# -*- Mode: Python; test-case-name: flumotion.test.test_component_httpserver -*-
# vi:si:et:sw=4:sts=4:ts=4
#
# Flumotion - a streaming media server
# Copyright (C) 2004,2005,2006,2007 Fluendo, S.L. (www.fluendo.com).
# All rights reserved.

# This file may be distributed and/or modified under the terms of
# the GNU General Public License version 2 as published by
# the Free Software Foundation.
# This file is distributed without any warranty; without even the implied
# warranty of merchantability or fitness for a particular purpose.
# See "LICENSE.GPL" in the source distribution for more information.

# Licensees having purchased or holding a valid Flumotion Advanced
# Streaming Server license may use this file in accordance with the
# Flumotion Advanced Streaming Server Commercial License Agreement.
# See "LICENSE.Flumotion" in the source distribution for more information.

# Headers in this file shall remain intact.
import os
import time
import string

from twisted.web import resource, static, server, http
from twisted.web import error as weberror
from twisted.internet import defer, reactor, error
from twisted.cred import credentials
from zope.interface import implements

from flumotion.component import component
from flumotion.common import log, messages, errors, netutils, interfaces
from flumotion.component.component import moods
from flumotion.component.misc.porter import porterclient
from flumotion.component.base import http as httpbase

from flumotion.twisted import fdserver

from flumotion.component.misc.httpfile import file

from flumotion.common.messages import N_
T_ = messages.gettexter('flumotion')

class CancellableRequest(server.Request):

    def __init__(self, channel, queued):
        server.Request.__init__(self, channel, queued)

        self._component = channel.factory.component
        self._completed = False
        self._transfer = None

        self._bytes_written = 0
        self._start_time = time.time()
        self._lastTimeWritten = self._start_time

        self._component.requestStarted(self)

    def write(self, data):
        server.Request.write(self, data)

        self._bytes_written += len(data)
        self._lastTimeWritten = time.time()
        
    def finish(self):
        server.Request.finish(self)
        fd = self.transport.fileno()
        # We sent Connection: close, so we must close the connection
        self.transport.loseConnection()
        self.requestCompleted(fd)

    def connectionLost(self, reason):
        fd = self.transport.fileno()
        server.Request.connectionLost(self, reason)
        self.requestCompleted(fd)

    def requestCompleted(self, fd):
        if not self._completed:
            self._component.requestFinished(self, self._bytes_written, 
                time.time() - self._start_time, fd)
            self._completed = True
    
class Site(server.Site):
    requestFactory = CancellableRequest

    def __init__(self, resource, component):
        server.Site.__init__(self, resource)

        self.component = component

class HTTPFileMedium(component.BaseComponentMedium):
    def __init__(self, comp):
        """
        @type comp: L{HTTPFileStreamer}
        """
        component.BaseComponentMedium.__init__(self, comp)

    def authenticate(self, bouncerName, keycard):
        """
        @rtype: L{twisted.internet.defer.Deferred} firing a keycard or None.
        """
        return self.callRemote('authenticate', bouncerName, keycard)

    def keepAlive(self, bouncerName, issuerName, ttl):
        """
        @rtype: L{twisted.internet.defer.Deferred}
        """
        return self.callRemote('keepAlive', bouncerName, issuerName, ttl)

    def removeKeycardId(self, bouncerName, keycardId):
        """
        @rtype: L{twisted.internet.defer.Deferred}
        """
        return self.callRemote('removeKeycardId', bouncerName, keycardId)

    def remote_getStreamData(self):
        return self.comp.getStreamData()

    def remote_getLoadData(self):
        return self.comp.getLoadData()

    def remote_updatePorterDetails(self, path, username, password):
        return self.comp.updatePorterDetails(path, username, password)

    def remote_rotateLog(self):
        return self.comp.rotateLog()

class HTTPFileStreamer(component.BaseComponent, httpbase.HTTPAuthentication, 
    log.Loggable):
    implements(interfaces.IStreamingComponent)

    componentMediumClass = HTTPFileMedium

    REQUEST_TIMEOUT = 30 # Time out requests after this many seconds of 
                         # inactivity

    def __init__(self):
       component.BaseComponent.__init__(self)
       httpbase.HTTPAuthentication.__init__(self, self)

    def init(self):
        self.mountPoint = None
        self.type = None
        self.port = None
        self.hostname = None
        self._loggers = []
        self._logfilter = None

        self._description = 'On-Demand Flumotion Stream',

        self._singleFile = False
        self._connected_clients = []
        self._total_bytes_written = 0

        self._pbclient = None

        self._twistedPort = None
        self._timeoutRequestsCallLater = None

        # FIXME: maybe we want to allow the configuration to specify
        # additional mime -> File class mapping ?
        self._mimeToResource = {
            'video/x-flv': file.FLVFile,
        }

        # store number of connected clients
        self.uiState.addKey("connected-clients", 0)
        self.uiState.addKey("bytes-transferred", 0)

    def getDescription(self):
        return self._description

    def do_setup(self):
        props = self.config['properties']

        desc = props.get('description', None)
        if desc:
            self._description = desc

        # always make sure the mount point starts with /
        mountPoint = props.get('mount-point', '/')
        if not mountPoint.startswith('/'):
            mountPoint = '/' + mountPoint
        self.mountPoint = mountPoint
        self.hostname = props.get('hostname', None)
        if not self.hostname:
            self.hostname = netutils.guess_public_hostname()

        self.filePath = props.get('path')
        self.type = props.get('type', 'master')
        self.port = props.get('port', 8801)
        if self.type == 'slave':
            # already checked for these in do_check
            self._porterPath = props['porter-socket-path']
            self._porterUsername = props['porter-username']
            self._porterPassword = props['porter-password']
        self._loggers = \
            self.plugs.get('flumotion.component.plugs.loggers.Logger', [])

        if 'bouncer' in props:
            self.setBouncerName(props['bouncer'])
        if 'issuer-class' in props:
            self.setIssuerClass(props['issuer-class'])
        if 'ip-filter' in props:
            filter = http.LogFilter()
            for f in props['ip-filter']:
                filter.addIPFilter(f)
            self._logfilter = filter

    def do_stop(self):
        self.stopKeepAlive()
        if self._timeoutRequestsCallLater:
            self._timeoutRequestsCallLater.cancel()
            self._timeoutRequestsCallLater = None
        if self._twistedPort:
            self._twistedPort.stopListening()

        if self.type == 'slave' and self._pbclient:
            return self._pbclient.deregisterPath(self.mountPoint)

        return component.BaseComponent.do_stop(self)

    def updatePorterDetails(self, path, username, password):
        """
        Provide a new set of porter login information, for when we're in slave
        mode and the porter changes.
        If we're currently connected, this won't disconnect - it'll just change
        the information so that next time we try and connect we'll use the
        new ones
        """
        if self.type == 'slave':
            self._porterUsername = username
            self._porterPassword = password

            creds = credentials.UsernamePassword(self._porterUsername, 
                self._porterPassword)
            self._pbclient.startLogin(creds, self.medium)

            # If we've changed paths, we must do some extra work.
            if path != self._porterPath:
                self._porterPath = path
                self._pbclient.stopTrying() # Stop trying to connect with the
                                            # old connector.
                self._pbclient.resetDelay()
                reactor.connectWith(
                    fdserver.FDConnector, self._porterPath, 
                    self._pbclient, 10, checkPID=False)
        else:
            raise errors.WrongStateError(
                "Can't specify porter details in master mode")

    def do_start(self, *args, **kwargs):
        self.debug('Starting with mount point "%s"' % self.mountPoint)
        factory = file.MimedFileFactory(self,
            mimeToResource=self._mimeToResource)
        if self.mountPoint == '/':
            self.debug('mount point / - create File resource as root')
            # directly create a File resource for the path
            root = factory.create(self.filePath)
        else:
            # split path on / and add iteratively twisted.web resources
            # Asking for '' or '/' will retrieve the root Resource's '' child,
            # so the split on / returning a first list value '' is correct
            self.debug('mount point %s - creating root Resource and children',
                self.mountPoint)
            root = resource.Resource()
            children = string.split(self.mountPoint[1:], '/')
            parent = root
            for child in children[:-1]:
                res = resource.Resource()
                self.debug("Putting Resource at %s", child)
                parent.putChild(child, res)
                parent = res
            fileResource = factory.create(self.filePath)
            self.debug("Putting resource %r at %r", fileResource, children[-1])
            parent.putChild(children[-1], fileResource)

        self._timeoutRequestsCallLater = reactor.callLater(
            self.REQUEST_TIMEOUT, self._timeoutRequests)

        d = defer.Deferred()
        if self.type == 'slave':
            # Streamer is slaved to a porter.
            if self._singleFile:
                self._pbclient = porterclient.HTTPPorterClientFactory(
                    Site(root, self), [self.mountPoint], d)
            else:
                self._pbclient = porterclient.HTTPPorterClientFactory(
                    Site(root, self), [], d, 
                    prefixes=[self.mountPoint])
            creds = credentials.UsernamePassword(self._porterUsername, 
                self._porterPassword)
            self._pbclient.startLogin(creds, self.medium)
            self.debug("Starting porter login!")
            # This will eventually cause d to fire
            reactor.connectWith(fdserver.FDConnector, self._porterPath, 
                self._pbclient, 10, checkPID=False)
        else:
            # File Streamer is standalone.
            try:
                self.debug('Going to listen on port %d' % self.port)
                iface = ""
                # we could be listening on port 0, in which case we need
                # to figure out the actual port we listen on
                self._twistedPort = reactor.listenTCP(self.port,
                    Site(root, self), interface=iface)
                self.port = self._twistedPort.getHost().port
                self.debug('Listening on port %d' % self.port)
            except error.CannotListenError:
                t = 'Port %d is not available.' % self.port
                self.warning(t)
                m = messages.Error(T_(N_(
                    "Network error: TCP port %d is not available."), self.port))
                self.addMessage(m)
                self.setMood(moods.sad)
                return defer.fail(errors.ComponentStartHandledError(t))
            # fire callback so component gets happy
            d.callback(None)
        # we are responsible for setting component happy
        def setComponentHappy(result):
            self.scheduleKeepAlive()
            self.setMood(moods.happy)
            return result
        d.addCallback(setComponentHappy)
        return d

    def do_check(self):
        props = self.config['properties']
        self.fixRenamedProperties(props, [
            ('issuer',             'issuer-class'),
            ('porter_socket_path', 'porter-socket-path'),
            ('porter_username',    'porter-username'),
            ('porter_password',    'porter-password'),
            ('mount_point',        'mount-point')
            ])

        if props.get('type', 'master') == 'slave':
            for k in 'socket-path', 'username', 'password':
                if not 'porter-' + k in props:
                    msg = 'slave mode, missing required property porter-%s' % k
                    return defer.fail(errors.ConfigError(msg))

            path = props.get('path', None) 
            if path is None: 
                msg = "missing required property 'path'"
                return defer.fail(errors.ConfigError(msg)) 
            if os.path.isfile(path):
                self._singleFile = True
            elif os.path.isdir(path):
                self._singleFile = False
            else:
                msg = "the file or directory specified in 'path': %s does " \
                    "not exist or is neither a file nor directory" % path
                return defer.fail(errors.ConfigError(msg)) 

    def _timeoutRequests(self):
        now = time.time()
        for request in self._connected_clients:
            if now - request._lastTimeWritten > self.REQUEST_TIMEOUT:
                self.debug("Timing out connection")
                # Apparently this is private API. However, calling 
                # loseConnection is not sufficient - it won't drop the
                # connection until the send queue is empty, which might never 
                # happen for an uncooperative client
                request.channel.transport.connectionLost(
                    errors.TimeoutException())

        self._timeoutRequestsCallLater = reactor.callLater(
            self.REQUEST_TIMEOUT, self._timeoutRequests)
            
    def requestStarted(self, request):
        self._connected_clients.append(request)
        self.uiState.set("connected-clients", len(self._connected_clients))

    def requestFinished(self, request, bytesWritten, timeConnected, fd):
        self.cleanupAuth(fd)
        headers = request.getAllHeaders()

        ip = request.getClientIP()
        if not self._logfilter or not self._logfilter.isInRange(ip):
            args = {'ip': ip,
                    'time': time.gmtime(),
                    'method': request.method,
                    'uri': request.uri,
                    'username': '-', # FIXME: put the httpauth name
                    'get-parameters': request.args,
                    'clientproto': request.clientproto,
                    'response': request.code,
                    'bytes-sent': bytesWritten,
                    'referer': headers.get('referer', None),
                    'user-agent': headers.get('user-agent', None),
                    'time-connected': timeConnected}

            for logger in self._loggers:
                logger.event('http_session_completed', args)

        self._connected_clients.remove(request)

        self.uiState.set("connected-clients", len(self._connected_clients))

        self._total_bytes_written += bytesWritten
        self.uiState.set("bytes-transferred", self._total_bytes_written)

    def getUrl(self):
        return "http://%s:%d%s" % (self.hostname, self.port, self.mountPoint)

    def getStreamData(self):
        socket = 'flumotion.component.plugs.streamdata.StreamDataProvider'
        if self.plugs[socket]: 
            plug = self.plugs[socket][-1] 
            return plug.getStreamData()
        else:
            return {
                'protocol': 'HTTP',
                'description': self._description,
                'url' : self.getUrl()
                }

    def getLoadData(self):
        """
        Return a tuple (deltaadded, deltaremoved, bytes_transferred, 
        current_clients, current_load) of our current bandwidth and user values.
        The deltas and current_load are NOT currently implemented here, we set 
        them as zero.
        """
        bytesTransferred = self._total_bytes_written
        for request in self._connected_clients:
            if request._transfer:
                bytesTransferred += request._transfer.bytesWritten

        return (0, 0, bytesTransferred, len(self._connected_clients), 0)

    # Override HTTPAuthentication methods
    def authenticateKeycard(self, bouncerName, keycard):
        return self.medium.authenticate(bouncerName, keycard)

    def keepAlive(self, bouncerName, issuerName, ttl):
        return self.medium.authenticate(bouncerName, issuerName, ttl)

    def cleanupKeycard(self, bouncerName, keycard):
        return self.medium.removeKeycardId(bouncerName, keycard.id)

    def clientDone(self, fd):
        # TODO: implement this properly.
        self.warning ("Expiring clients is not implemented for static "
            "fileserving")

    def rotateLog(self):
        """
        Close the logfile, then reopen using the previous logfilename
        """
        for logger in self._loggers:
            self.debug('rotating logger %r' % logger)
            logger.rotate()

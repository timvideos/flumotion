# -*- Mode: Python -*-
# vi:si:et:sw=4:sts=4:ts=4

# Flumotion - a streaming media server
# Copyright (C) 2004,2005,2006,2007,2008,2009 Fluendo, S.L.
# Copyright (C) 2010,2011 Flumotion Services, S.A.
# All rights reserved.
#
# This file may be distributed and/or modified under the terms of
# the GNU Lesser General Public License version 2.1 as published by
# the Free Software Foundation.
# This file is distributed without any warranty; without even the implied
# warranty of merchantability or fitness for a particular purpose.
# See "LICENSE.LGPL" in the source distribution for more information.
#
# Headers in this file shall remain intact.

from gi.repository import GObject
from gi.repository import Gst
from gi.repository import GLib

from twisted.internet import reactor

from flumotion.component.common.fgdp import protocol as fgdp

GDP_TYPE_PRODUCER = "producer-type"
GDP_TYPE_CONSUMER = "consumer-type"

Gst.init(None)

class FDHandler(object):
    """
    Base class for elements handling file descriptors

    @type  fdelement: L{Gst.Element}
    """

    def __init__(self, fdelement):
        self.fdelement = fdelement

    ### FDHandler interface for subclasses

    def connectFd(self, fd):
        '''
        Connects a file descriptor to the gstreamer element that will be
        writting to it or reading from it

        @type  fd: int
        '''
        raise NotImplemented("subclass must implement connectFD")

    def disconnectFd(self, fd):
        '''
        Disconnects a file descriptor from the gstreamer element that is
        writting to it or reading from it

        @type  fd: int
        '''
        raise NotImplemented("subclass must implement disconnectFD")


class FDSrc(FDHandler):
    """
    File descriptors handler based on fdsrc

    @type  protocol: L{flummotion.common.gdp_protocol.FGDPBaseProtocol}
    """

    logCategory = 'gdp-producer'

    protocol = None
    _handler_id = None

    def __init__(self, fdelement):
        FDHandler.__init__(self, fdelement)

    def _check_eos(self, pad, event):
        if event.get_event().type == Gst.EventType.EOS:
            # EOS are triggered after a disconnection, when the read in the
            # socket is 0 Bytes. Remove the handler and close the connection
            pad.remove_probe(self._handler_id)
            if self.protocol is not None:
                reactor.callFromThread(self.protocol.loseConnection)
            return False
        return True

    def connectFd(self, fd):
        # Unlock the state of the element, which should be already in the READY
        # state. Add the fd and an event probe to detect disconnections
        self.fdelement.set_locked_state(False)
        self.fdelement.set_property('fd', fd)
        srcpad = self.fdelement.get_static_pad("src")
        self._handler_id = srcpad.add_probe(Gst.PadProbeType.EVENT_BOTH, self._check_eos, None)
        self.fdelement.set_state(Gst.State.PLAYING)

    def disconnectFd(self, _):
        # Set back the element to the READY state, in which a fd can be
        # added/changed and lock the state of the element
        self.fdelement.set_state(Gst.State.READY)
        self.fdelement.get_state(0)
        self.fdelement.set_locked_state(True)


class MultiFDSink(FDHandler):
    """
    File descriptors handler based on fdsrc

    @type  protocol: L{flummotion.common.gdp_protocol.FGDPBaseProtocol}
    """

    logCategory = 'gdp-consumer'

    protocol = None
    _activeFD = None
    _handler_id = None

    def __init__(self, fdelement):
        FDHandler.__init__(self, fdelement)

    def _on_client_removed(self, a, fd):
        if self.protocol is not None:
            reactor.callFromThread(self.protocol.loseConnection)
        self.fdelement.handler_disconnect(self._handler_id)

    def connectFd(self, fd):
        self.fdelement.emit('add', fd)
        self._activeFD = fd
        self._handler_id = self.fdelement.connect('client-fd-removed',
                                                  self._on_client_removed)

    def disconnectFd(self, fd):
        if self._activeFD == fd:
            self.fdelement.emit('remove', fd)
            self._activeFD = None


class _ProtocolMixin(object):
    """
    Provides an abstraction for the start and stop of a client or server using
    the FGDP protocol, which depends on the 'mode' selected amongst 'push' or
    'pull'

    @type  mode:     str
    @type  host:     str
    @type  port:     int
    """

    mode = ''
    host = None
    port = None
    _listener = None
    _connector = None

    def start(self):
        """
        Starts a server/client using the FGDP protocol when the element
        is ready.
        """
        if self.mode == 'push':
            self._start_push()
        else:
            self._start_pull()

    def stop(self):
        """
        Stops the server/client using the FGDP protocol.
        """
        if self._listener is not None:
            self._listener.stopListening()

        if self._connector is not None:
            self._connector.disconnect()

    def _start_push(self):
        #self.info("Starting fgdp client")
        factory = fgdp.FGDPClientFactory(self)
        self._connector = reactor.connectTCP(self.host, self.port, factory)

    def _start_pull(self):
        #self.info("Starting fgdp server")
        factory = fgdp.FGDPServerFactory(self)
        self._listener = reactor.listenTCP(self.port, factory)


class FGDPBase(Gst.Bin, _ProtocolMixin):
    """
    Base class for gstreamer elements using the FGDP protocol
    """

    mode = 'pull'
    host = 'localhost'
    port = 15000
    username = 'user'
    password = 'test'
    maxDelay = 5
    version = '0.1'

    __gproperties__ = {
        'mode': (GObject.TYPE_STRING, 'mode',
            "Connection mode: 'pull' or 'push'",
            'pull', GObject.PARAM_READWRITE),
        'host': (GObject.TYPE_STRING, 'host',
            'Name of the host to connect (in push mode)',
            'localhost', GObject.PARAM_READWRITE),
        'port': (GObject.TYPE_INT, 'port',
            'Connection port',
            1, 64000, 15000, GObject.PARAM_READWRITE),
        'username': (GObject.TYPE_STRING, 'user name',
            'Username for the authentication',
            'user', GObject.PARAM_READWRITE),
        'password': (GObject.TYPE_STRING, 'password',
            'Password for the authentication',
            'test', GObject.PARAM_READWRITE),
        'version': (GObject.TYPE_STRING, 'version',
            'Protocol version',
            '0.1', GObject.PARAM_READWRITE),
        'max-reconnection-delay': (GObject.TYPE_FLOAT,
            'maximum delay between reconnections in seconds',
            'Maximum delay between reconnections in seconds (for push mode)',
            1, 100, 5, GObject.PARAM_READWRITE)}

    __gsignals__ = {"connected": (GObject.SignalFlags.RUN_LAST,\
                                  None, []),
                    "disconnected": (GObject.SignalFlags.RUN_LAST,\
                                     None,
                                     (GObject.TYPE_STRING, ))}

    def _handle_error(self, message):
        err = GLib.GError(Gst.resource_error_quark(),
                         Gst.ResourceError.FAILED, message)
        m = Gst.Message.new_error(self, err, message)
        self.post_message(m)
        self.error(message)

    def do_change_state(self, transition):
        if transition == Gst.StateChange.READY_TO_PAUSED:
            try:
                self.prepare()
                self.start()
            except Exception, e:
                self._handle_error(str(e))
                self.stop()
                return Gst.StateChange.FAILURE
        elif transition == Gst.StateChange.PAUSED_TO_READY:
            self.stop()
        return Gst.Bin.do_change_state(self, transition)

    def do_set_property(self, prop, value):
        if prop.name in ['mode', 'host', 'username', 'password', 'port',
                         'version']:
            setattr(self, prop.name, value)
        elif prop.name == 'max-reconnection-delay':
            self.maxDelay = float(value)
        else:
            raise AttributeError('unknown property %s' % prop.name)

    def do_get_property(self, prop):
        if prop.name in ['mode', 'host', 'username', 'password', 'port',
                         'version']:
            return getattr(self, prop.name)
        if prop.name == 'max-reconnection-delay':
            return self.maxDelay
        raise AttributeError('unknown property %s' % prop.name)

    def prepare(self):
        """
        Should be implemented by subclasses that needs to do something
        before starting the server/client
        """
        pass


class FGDPSink(FGDPBase, MultiFDSink):
    '''
    GStreamer sink element using the FGDP protocol
    '''

    mode = 'push'

    __gstdetails__ = ('FGDPsink', 'Sink',
                      'Flumotion GStreamer data protocol sink',
                      'Flumotion DevTeam')

    def __init__(self):
        FGDPBase.__init__(self)
        # Create elements
        gdppay = Gst.ElementFactory.make('gdppay')
        self.fdelement = Gst.ElementFactory.make('multifdsink')
        # Set default properties
        self.fdelement.set_property('sync', False)
        self.fdelement.set_property('units-max', 1 * Gst.SECOND)
        self.fdelement.set_property('units-soft-max', 700 * Gst.MSECOND)
        self.fdelement.set_property('recover-policy', 1)
        # Create fd handler proxy
        MultiFDSink.__init__(self, self.fdelement)
        # Add elements to the bin and link them
        self.add(gdppay, self.fdelement)
        gdppay.link(self.fdelement)
        # Create sink pads
        self._sink_pad = Gst.GhostPad.new('sink', gdppay.get_static_pad('sink'))
        self.add_pad(self._sink_pad)


class FGDPSrc(FGDPBase, FDSrc):
    '''
    GStreamer source element using the FGDP protocol
    '''

    mode = 'pull'

    __gstdetails__ = ('FGDPsrc', 'Source',
                      'Flumotion GStreamer data protocol source',
                      'Flumotion DevTeam')

    def __init__(self):
        FGDPBase.__init__(self)
        # Create elements
        self.fdelement = Gst.ElementFactory.make('fdsrc')
        gdpdepay = Gst.ElementFactory.make('gdpdepay')
        # Add elements to the bin and link them
        self.add(self.fdelement, gdpdepay)
        self.fdelement.link(gdpdepay)
        # Create fd handler proxy
        FDSrc.__init__(self, self.fdelement)
        # Create sink pads
        self._src_pad = Gst.GhostPad.new('src', gdpdepay.get_static_pad('src'))
        self.add_pad(self._src_pad)

    def prepare(self):
        # Lock the state until we get the first connection and we can pass it
        # a valid fd, otherwhise it will be using stdin.
        self.fdelement.set_locked_state(True)


def plugin_init(plugin, userarg):
    name = plugin.get_name()
    pluginType = GObject.type_register(userarg)
    Gst.Element.register(plugin, name, Gst.Rank.MARGINAL, pluginType)
    return True

version = Gst.version()

Gst.Plugin.register_static_full(
    version[0],  # GST_VERSION_MAJOR
    version[1],  # GST_VERSION_MINOR
    'fgdpsink',
    'fgdp sink plugin',
    plugin_init,
    '12.06',
    'LGPL',
    'fgdp',
    'fgdp',
    '',
    FGDPSink,
)

Gst.Plugin.register_static_full(
    version[0],  # GST_VERSION_MAJOR
    version[1],  # GST_VERSION_MINOR
    'fgdpsrc',
    'fgdp src plugin',
    plugin_init,
    '12.06',
    'LGPL',
    'fgdp',
    'fgdp',
    '',
    FGDPSrc,
)
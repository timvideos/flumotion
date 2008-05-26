# -*- Mode: Python; test-case-name: flumotion.test.test_feedcomponent010 -*-
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

"""
Base classes for component UI's using GTK+
"""

import gettext
import os
import time

import gtk
import gtk.glade
from twisted.python import util
from twisted.internet import defer
from zope.interface import implements

from flumotion.common import errors, log, common, messages
from flumotion.common.format import formatStorage, formatTime, formatTimeStamp
from flumotion.common.i18n import N_, getLL, gettexter
from flumotion.common.planet import AdminFlowState
from flumotion.configure import configure
from flumotion.extern.log.log import getDebug
from flumotion.twisted import flavors
from flumotion.ui.fgtk import ProxyWidgetMapping

_ = gettext.gettext
__version__ = "$Rev$"
T_ = gettexter()


class BaseAdminGtk(log.Loggable):
    """
    I am a base class for all GTK+-based Admin views.
    I am a view on one component's properties.

    @type nodes: L{twisted.python.util.OrderedDict}
    @ivar nodes: an ordered dict of name -> L{BaseAdminGtkNode}
    """

    logCategory = "admingtk"
    gettextDomain = None

    def __init__(self, state, admin):
        """
        @param state: state of component this is a UI for
        @type  state: L{flumotion.common.planet.AdminComponentState}
        @type  admin: L{flumotion.admin.admin.AdminModel}
        @param admin: the admin model that interfaces with the manager for us
        """
        self._debugEnabled = False
        self.state = state
        self.name = state.get('name')
        self.admin = admin
        self.debug('creating admin gtk for state %r' % state)
        self.uiState = None
        self.nodes = util.OrderedDict()

        d = admin.componentCallRemote(state, 'getUIState')
        d.addCallback(self.setUIState)

    def setDebugEnabled(self, enabled):
        """Set if debug should be enabled.
        Not all pages are visible unless debugging is set to true

        @param enabled: whether debug should be enabled
        @type  enabled: bool
        """
        self._debugEnabled = enabled
        for node in self.getNodes().values():
            node.setDebugEnabled(enabled)

    def cleanup(self):
        if self.uiState:
            self.uiState.removeListener(self)
            self.uiState = None
        for node in self.getNodes().values():
            node.cleanup()

    def setUIState(self, state):
        self.debug('starting listening to state %r', state)
        state.addListener(self, self.stateSet, self.stateAppend,
                          self.stateRemove)
        self.uiState = state
        for node in self.getNodes().values():
            node.gotUIState(state)
        self.uiStateChanged(state)

    def callRemote(self, methodName, *args, **kwargs):
        return self.admin.componentCallRemote(self.state, methodName,
                                              *args, **kwargs)

    # FIXME: .setup() is subclassable, while .render() on nodes has
    # haveWidgetTree.  choose one of the two patterns in general
    def setup(self):
        """
        Set up the admin view so it can display nodes.
        """
        self.debug('BaseAdminGtk.setup()')

        def fetchTranslations():
            if not self.gettextDomain:
                return defer.succeed(None)

            def haveBundle(localedatadir):
                localeDir = os.path.join(localedatadir, 'locale')
                self.debug("Loading locales for %s from %s" % (
                    self.gettextDomain, localeDir))
                # import done here due to defgen scoping issues
                import gettext
                gettext.bindtextdomain(self.gettextDomain, localeDir)
                gtk.glade.bindtextdomain(self.gettextDomain, localeDir)


            lang = getLL()
            self.debug("loading bundle for %s locales" % lang)
            bundleName = '%s-locale-%s' % (self.gettextDomain, lang)
            d = self.admin.bundleLoader.getBundleByName(bundleName)
            d.addCallbacks(haveBundle, lambda _: None)
            return d

        def addPages(_):
            # FIXME: node order should be fixed somehow, so e.g. Component
            # always comes last, together with eater/feeder ?

            # add a generic component node
            self.nodes['Component'] = ComponentAdminGtkNode(self.state,
                self.admin)

            config = self.state.get('config')

            # add feeder node, if component has feeders
            if config['feed']:
                self.debug("Component has feeders, show Feeders node")
                self.nodes['Feeders'] = FeedersAdminGtkNode(
                    self.state, self.admin)

            # add eater node, if component has eaters
            if 'eater' in config and config['eater']:
                self.debug("Component has eaters, show Eaters node")
                self.nodes['Eaters'] = EatersAdminGtkNode(
                    self.state, self.admin)

        d = fetchTranslations()
        d.addCallback(addPages)

        # FIXME: why are we not returning the deferred here ? If there is
        # a good reason, it should be commented here
        return

    def getNodes(self):
        """
        Return a dict of admin UI nodes.

        @rtype:   dict of str -> L{BaseAdminGtkNode}
        @returns: dict of name (untranslated) -> admin node
        """
        return self.nodes

    # FIXME: deprecated
    def render(self):
        """
        Render the GTK+ admin view for this component and return the
        main widget for embedding.
        """
        raise NotImplementedError

    def uiStateChanged(self, stateObject):
        # so, this is still here, but I'd prefer people to (1) just use
        # the nodes and not the global admin; and (2) use the state
        # listener stuff more than the chunkier 'uistatechanged'
        pass

    def stateSet(self, object, key, value):
        self.uiStateChanged(object)

    def stateAppend(self, object, key, value):
        self.uiStateChanged(object)

    def stateRemove(self, object, key, value):
        self.uiStateChanged(object)

class BaseAdminGtkNode(log.Loggable):
    """
    I am a base class for all GTK+-based Admin UI nodes.
    I am a view on a set of properties for a component.

    @ivar widget: the main widget representing this node
    @type widget: L{gtk.Widget}
    @ivar wtree:  the widget tree representation for this node
    """

    implements(flavors.IStateListener)

    logCategory = "admingtk"
    gladeFile = None ## Relative path of the glade file.
                      ##   e.g. "flumotion/ui.glade"
    gettextDomain = configure.PACKAGE

    def __init__(self, state, admin, title=None):
        """
        @param state: state of component this is a UI node for
        @type  state: L{flumotion.common.planet.AdminComponentState}
        @param admin: the admin model that interfaces with the manager for us
        @type  admin: L{flumotion.admin.admin.AdminModel}
        @param title: the (translated) title to show this node with
        @type  title: str
        """
        self._debugEnabled = False
        self.state = state
        self.admin = admin
        self.statusbar = None
        self.title = title
        self.nodes = util.OrderedDict()
        self.wtree = None
        self.widget = None
        self.uiState = None # set if we are listening
        self._pendingUIState = None # set if we are waiting for the ui
                                    # to load
        ## Absolute path to the glade file.
        ##   e.g. "/home/flu/.flumotion/cache/test/80...df7/flumotion/ui.glade
        self._gladefilepath = None

    def setDebugEnabled(self, enabled):
        """Set if debug should be enabled.
        Not all pages are visible unless debugging is set to true

        @param enabled: whether debug should be enabled
        @type  enabled: bool
        """
        self._debugEnabled = enabled

    def cleanup(self):
        if self.uiState:
            self.uiState.removeListener(self)

    def status_push(self, str):
        if self.statusbar:
            return self.statusbar.push('notebook', str)

    def status_pop(self, mid):
        if self.statusbar:
            return self.statusbar.remove('notebook', mid)

    def callRemote(self, methodName, *args, **kwargs):
        return self.admin.componentCallRemote(self.state, methodName,
                                              *args, **kwargs)

    # FIXME: do this automatically if there is a gladeFile class attr set
    def loadGladeFile(self, gladeFile, domain=configure.PACKAGE):
        """
        Returns: a deferred returning the widget tree from the glade file.
        """
        def _getBundledFileCallback(result, gladeFile):
            path = result
            if not os.path.exists(path):
                self.warning("Glade file %s not found in path %s" % (
                    gladeFile, path))
            self.debug("loading widget tree from %s" % path)

            old = gtk.glade.textdomain()
            self.debug("Switching glade text domain from %s to %s" % (
                old, domain))
            self._gladefilepath = path
            gtk.glade.textdomain(domain)

            self.wtree = gtk.glade.XML(path,
                                       typedict=ProxyWidgetMapping())

            self.debug("Switching glade text domain back from %s to %s" % (
                domain, old))
            gtk.glade.textdomain(old)
            return self.wtree

        # The manager is always using / as a path separator, to avoid
        # confusion, convert os.path.sep -> / here.
        gladeFile = gladeFile.replace(os.path.sep, '/')
        # FIXME: this does needless roundtrips; should instead be
        # loading from the already-downloaded paths
        self.debug("requesting bundle for glade file %s" % gladeFile)
        d = self.admin.bundleLoader.getFile(gladeFile)
        d.addCallback(_getBundledFileCallback, gladeFile)
        return d

    def getWidget(self, name):
        if not self.wtree:
            raise IndexError
        widget = self.wtree.get_widget(name)
        if not widget:
            self.warning('Could not get widget %s' % name)

        return widget

    def createWidget(self, name):
        """
        Create a new widget instance from the glade file.
        Can be used to make multiple instances of the same widget.
        """
        if not self._gladefilepath:
            raise IndexError
        wtree = gtk.glade.XML(self._gladefilepath, name,
                              typedict=ProxyWidgetMapping())
        widget = wtree.get_widget(name)
        if not widget:
            self.warning('Could not create widget %s' % name)

        return widget

    def haveWidgetTree(self):
        """
        I am called when the widget tree has been gotten from the glade
        file. Responsible for setting self.widget.

        Override me to act on it.
        """
        pass

    def gotUIState(self, state):
        if self.widget:
            self.setUIState(state)
        else:
            self._pendingUIState = state

    def setUIState(self, state):
        """
        Called by the BaseAdminGtk when it gets the UI state and the GUI
        is ready. Chain up if you provide your own implementation.
        """
        self.uiState = state
        state.addListener(self, self.stateSet, self.stateAppend,
                          self.stateRemove, self.stateSetitem,
                          self.stateDelitem)

    def stateSet(self, state, key, value):
        "Override me"
        pass

    def stateAppend(self, state, key, value):
        "Override me"
        pass

    def stateRemove(self, state, key, value):
        "Override me"
        pass

    def stateSetitem(self, state, key, subkey, value):
        "Override me"
        pass

    def stateDelitem(self, state, key, subkey, value):
        "Override me"
        pass

    def render(self):
        """
        Render the GTK+ admin view for this component.

        Returns: a deferred returning the main widget for embedding
        """
        # clear up previous error messages
        allmessages = self.state.get('messages', [])
        for message in allmessages:
            if message.id == 'render':
                self.debug('Removing previous messages %r' % message)
                self.state.observe_remove('messages', message)

        def error(debug):
            # add an error message to the component and return
            # an error label, given a debug string
            self.warning("error rendering component UI; debug %s", debug)
            m = messages.Error(T_(N_(
                "Internal error in component UI.  "
                "Please file a bug against the component.")),
                debug=debug, id="render")
            self.addMessage(m)

            label = gtk.Label(_("Internal error.\nSee component error "
                    "message\nfor more details."))

            # if we don't set this error as our label, we will raise
            # a TypeError below and obscure this more meaningful error
            self.widget = label

            return label

        def loadGladeFile():
            if not self.gladeFile:
                return defer.succeed(None)

            def haveWtree(wtree):
                self.wtree = wtree
                self.debug('render: calling haveWidgetTree')
                try:
                    self.haveWidgetTree()
                except Exception, e:
                    return error(log.getExceptionMessage(e))

            self.debug('render: loading glade file %s in text domain %s',
                       self.gladeFile, self.gettextDomain)

            d = self.loadGladeFile(self.gladeFile, self.gettextDomain)
            d.addCallback(haveWtree)
            return d

        def loadGladeFileErrback(failure):
            if failure.check(RuntimeError):
                return error(
                    'Could not load glade file %s.' % self.gladeFile)
            if failure.check(errors.NoBundleError):
                return error(
                    'No bundle found containing %s.' % self.gladeFile)

            return failure

        def renderFinished(_):
            if not self.widget:
                self.debug('render: no self.widget, failing')
                raise TypeError('no self.widget')

            if self._pendingUIState:
                self.debug('render: calling setUIState on the node')
                self.setUIState(self._pendingUIState)

            self.debug('renderFinished: returning widget %s', self.widget)
            return self.widget

        def renderFinishedErrback(failure):
            return error(log.getFailureMessage(failure))

        d = loadGladeFile()
        d.addErrback(loadGladeFileErrback)
        d.addCallback(renderFinished)
        d.addErrback(renderFinishedErrback)
        return d

    def addMessage(self, message):
        """
        Add a message to the component.
        Since this is called in a component view and only relevant to the
        component view, the message only exists in the view, and is not
        replicated to the manager state.

        The message will be displayed in the usual message view.

        @type  message: L{flumotion.common.messages.Message}
        """
        self.state.observe_append('messages', message)

# this class is a bit of an experiment
# editor's note: "experiment" is an excuse for undocumented and uncommented
class _StateWatcher(object):
    def __init__(self, state, setters, appenders, removers,
            setitemers=None, delitemers=None):
        self.state = state
        self.setters = setters
        self.appenders = appenders
        self.removers = removers
        self.setitemers = setitemers
        self.delitemers = delitemers
        self.shown = False

        state.addListener(self, set=self.onSet, append=self.onAppend,
                          remove=self.onRemove, setitem=self.onSetItem,
                          delitem=self.onDelItem)

        for k in appenders:
            for v in state.get(k):
                self.onAppend(state, k, v)

    def hide(self):
        if self.shown:
            for k in self.setters:
                self.onSet(self.state, k, None)
            self.shown = False

    def show(self):
        # "show" the watcher by triggering all the registered setters
        if not self.shown:
            self.shown = True
            for k in self.setters:
                self.onSet(self.state, k, self.state.get(k))

    def onSet(self, obj, k, v):
        if self.shown and k in self.setters:
            self.setters[k](self.state, v)

    def onAppend(self, obj, k, v):
        if k in self.appenders:
            self.appenders[k](self.state, v)

    def onRemove(self, obj, k, v):
        if k in self.removers:
            self.removers[k](self.state, v)

    def onSetItem(self, obj, k, sk, v):
        if self.shown and k in self.setitemers:
            self.setitemers[k](self.state, sk, v)

    def onDelItem(self, obj, k, sk, v):
        if self.shown and k in self.setitemers:
            self.setitemers[k](self.state, sk, v)

    def unwatch(self):
        if self.state:
            self.hide()
            for k in self.removers:
                for v in self.state.get(k):
                    self.onRemove(self.state, k, v)
            self.state.removeListener(self)
            self.state = None

class ComponentAdminGtkNode(BaseAdminGtkNode):
    gladeFile = os.path.join('flumotion', 'component', 'base',
        'component.glade')

    def __init__(self, state, admin):
        BaseAdminGtkNode.__init__(self, state, admin, title=_("Component"))

        self._startTime = None
        self._debugging = None
        self._initialFluMask = ''
        self._initialGstMask = ''
        
    def setDebugEnabled(self, enabled):
        BaseAdminGtkNode.setDebugEnabled(self, enabled)
        if self._debugging:
            self._debugging.set_property('visible', enabled)

        self._initialFluMask = getDebug()
        self._initialGstMask = os.environ.get('GST_DEBUG', '')
        
    def haveWidgetTree(self):
        self.widget = self.wtree.get_widget('main-vbox')
        assert self.widget, "No component-widget in %s" % self.gladeFile
        self.gst_mask = self.wtree.get_widget('gst_mask')
        self.gst_mask.connect('changed', self._on_gst_mask_changed)
        self.gst_label = self.wtree.get_widget('gst_label')
        self.flu_mask = self.wtree.get_widget('flu_mask')
        self.flu_mask.connect('changed', self._on_flu_mask_changed)
        self.gst_profile = self.wtree.get_widget('gst_profile')
        self.gst_profile.connect('changed', self._on_gst_profile_changed)
        self.flu_profile = self.wtree.get_widget('flu_profile')
        self.flu_profile.connect('changed', self._on_flu_profile_changed)

        # pid
        l = self.wtree.get_widget('label-pid')
        pid = self.state.get('pid')
        l.set_text(str(pid))

        # Find the labels which we'll update when we get uiState updates.
        self._label_start_time = self.wtree.get_widget('label-since')
        self._label_uptime = self.wtree.get_widget('label-uptime')
        self._label_cpu = self.wtree.get_widget('label-cpu')
        self._label_vsize = self.wtree.get_widget('label-vsize')

        self.widget.show()

        self._prepareDebugging()

        if self._initialFluMask:
            self.flu_mask.set_text(self._initialFluMask)
            self.flu_mask.emit('changed')
        if self._initialGstMask:
            self.gst_mask.set_text(self._initialGstMask)
            self.gst_mask.emit('changed')
        
        self._debugging = self.wtree.get_widget('debugging')
        if self._debugEnabled:
            self._debugging.show()

        return self.widget

    def _validateMask(self, mask):
        if ':' not in mask or mask.count(':') != 1:
            return False
        name, level = mask.split(':', 1)
        try:
            int(level)
        except ValueError:
            return False
        return True

    def _on_gst_profile_changed(self, combo):
        profile = combo.get_selected()
        if profile is not None:
            gtk.Entry.set_text(self.gst_mask, profile)
        self.gst_mask.set_sensitive(profile is None)

    def _on_flu_profile_changed(self, combo):
        profile = combo.get_selected()
        if profile is not None:
            gtk.Entry.set_text(self.flu_mask, profile)
        self.flu_mask.set_sensitive(profile is None)

    def _on_flu_mask_changed(self, entry):
        debug = entry.get_text()
        if not self._debugEnabled or not self._validateMask(debug):
            return
        self.admin.componentCallRemote(self.state, 'setFluDebug', debug)

    def _on_gst_mask_changed(self, entry):
        debug = entry.get_text()
        if not self._debugEnabled or not self._validateMask(debug):
            return
        self.admin.componentCallRemote(self.state, 'setGstDebug', debug)

    def _prepareDebugging(self):
        debugEnabled = self._debugEnabled
        self._debugEnabled = False
        default = [(_('Nothing'), '*:0'),
                   (_('Everything'), '*:4'),
                   (_('Custom'), None)]
        self.flu_profile.prefill(default)

        if isinstance(self.state.get('parent'), AdminFlowState):
            self.gst_profile.prefill(default)
        else:
            self.gst_profile.hide()
            self.gst_label.hide()
            self.gst_mask.hide()

        self._debugEnabled = debugEnabled

    def _setStartTime(self, value):
        self._label_start_time.set_text(
            time.strftime("%c", time.localtime(value)))
        self._label_uptime.set_text(formatTime(0))

        self._startTime = value

    def _setCurrentTime(self, value):
        if self._startTime is not None:
            runtime = value - self._startTime

            self._label_uptime.set_text(formatTime(runtime))
        else:
            self._label_uptime.set_text(_("not available"))

    def _updateCPU(self, cpu):
        # given float for cpu, update the label
        self._label_cpu.set_text('%.2f %%' % (cpu * 100.0))

    def _updateVSize(self, vsize):
        # given int for vsize in bytes, update the label
        if not vsize:
            self._label_vsize.set_text(_('Unknown'))
        else:
            self._label_vsize.set_text('%sB' % formatStorage(vsize))

    def setUIState(self, uiState):
        BaseAdminGtkNode.setUIState(self, uiState)

        # Ick; we don't get these otherwise.
        for key in uiState.keys():
            val = uiState.get(key)
            if val is not None:
                self.stateSet(uiState, key, uiState.get(key))

    # IStateListener Interface
    def stateSet(self, object, key, value):
        if key == 'cpu-percent':
            self._updateCPU(value)
        elif key == 'virtual-size':
            self._updateVSize(value)
        if key == 'start-time':
            self._setStartTime(value)
        elif key == 'current-time':
            self._setCurrentTime(value)

    def stateAppend(self, object, key, value):
        pass

    def stateRemove(self, object, key, value):
        pass

class FeedersAdminGtkNode(BaseAdminGtkNode):
    gladeFile = os.path.join('flumotion', 'component', 'base', 'feeders.glade')

    def __init__(self, state, admin):
        BaseAdminGtkNode.__init__(self, state, admin, title=_("Feeders"))
        # tree model is a model of id, uiState, _StateWatcher, type
        # tree model contains feeders and their feeder clients
        # type is a str, 'feeder' or 'client'
        self.treemodel = None
        self.treeview = None
        self.selected = None
        self.labels = {}
        self._lastConnect = 0
        self._lastDisconnect = 0

    def select(self, watcher):
        if self.selected:
            self.selected.hide()
        if watcher:
            self.selected = watcher
            self.selected.show()
        else:
            self.selected = None

    def setFeederName(self, state, value):
        self.labels['feeder-name'].set_markup(_('Feeder <b>%s</b>') % value)

    def _mungeClientId(self, clientId):
        try:
            flowName, compName, feedName = common.parseFullFeedId(clientId)
            return common.feedId(compName, feedName)
        except:
            return clientId

    def setFeederClientName(self, state, value):
        if not value:
            self.labels['eater-name'].set_markup(_('<i>select an eater</i>'))
            return
        value = self._mungeClientId(value)
        self.labels['eater-name'].set_markup(_('<b>%s</b>')
                                             % (value,))

    def setFeederClientBytesReadCurrent(self, state, value):
        txt = value and (formatStorage(value) + _('Byte')) or ''
        self.labels['bytes-read-current'].set_text(txt)
        self.updateConnectionTime()
        self.updateDisconnectionTime()

    def setFeederClientBuffersDroppedCurrent(self, state, value):
        if value is None:
            # no support for counting dropped buffers
            value = _("Unknown")
        self.labels['buffers-dropped-current'].set_text(str(value))
        self.updateConnectionTime()
        self.updateDisconnectionTime()

    def setFeederClientBytesReadTotal(self, state, value):
        txt = value and (formatStorage(value) + _('Byte')) or ''
        self.labels['bytes-read-total'].set_text(txt)

    def setFeederClientBuffersDroppedTotal(self, state, value):
        if value is None:
            # no support for counting dropped buffers
            value = _("Unknown")
        self.labels['buffers-dropped-total'].set_text(str(value))

    def setFeederClientReconnects(self, state, value):
        self.labels['connections-total'].set_text(str(value))

    def setFeederClientLastConnect(self, state, value):
        if value:
            text = formatTimeStamp(time.localtime(value))
            self.labels['connected-since'].set_text(text)
            self._lastConnect = value
            self.updateConnectionTime()

    def setFeederClientLastDisconnect(self, state, value):
        if value:
            text = formatTimeStamp(time.localtime(value))
            self.labels['disconnected-since'].set_text(text)
            self._lastDisconnect = value
            self.updateDisconnectionTime()

    def setFeederClientLastActivity(self, state, value):
        if value:
            text = formatTimeStamp(time.localtime(value))
            self.labels['last-activity'].set_text(text)

    def setFeederClientFD(self, state, value):
        if value == None:
            # disconnected
            self._table_connected.hide()
            self._table_disconnected.show()
        else:
            self._table_disconnected.hide()
            self._table_connected.show()

    # FIXME: add a timeout to update this ?
    def updateConnectionTime(self):
        if self._lastConnect:
            text = formatTime(time.time() - self._lastConnect)
            self.labels['connection-time'].set_text(text)

    # FIXME: add a timeout to update this ?
    def updateDisconnectionTime(self):
        if self._lastDisconnect:
            text = formatTime(time.time() - self._lastDisconnect)
            self.labels['disconnection-time'].set_text(text)

    def addFeeder(self, uiState, state):
        """
        @param uiState: the component's uiState
        @param state:   the feeder's uiState
        """
        feederName = state.get('feederName')
        i = self.treemodel.append(None)
        self.treemodel.set(i, 0, feederName, 1, state)
        w = _StateWatcher(state,
                          {'feederName': self.setFeederName},
                          {'clients': self.addFeederClient},
                          {'clients': self.removeFeederClient})
        self.treemodel.set(i, 2, w, 3, 'feeder')
        self.treeview.expand_all()

    # FIXME: this docstring is confusing
    def addFeederClient(self, feederState, state):
        """
        @param feederState: the component's uiState
        @param state:       the feeder client's uiState
        """

        printableClientId = self._mungeClientId(state.get('clientId'))
        for row in self.treemodel:
            if self.treemodel.get_value(row.iter, 1) == feederState:
                break
        i = self.treemodel.append(row.iter)
        self.treemodel.set(i, 0, printableClientId, 1, state)
        w = _StateWatcher(state, {
            'clientId':              self.setFeederClientName,
            'bytesReadCurrent':      self.setFeederClientBytesReadCurrent,
            'buffersDroppedCurrent': self.setFeederClientBuffersDroppedCurrent,
            'bytesReadTotal':        self.setFeederClientBytesReadTotal,
            'buffersDroppedTotal':   self.setFeederClientBuffersDroppedTotal,
            'reconnects':            self.setFeederClientReconnects,
            'lastConnect':           self.setFeederClientLastConnect,
            'lastDisconnect':        self.setFeederClientLastDisconnect,
            'lastActivity':          self.setFeederClientLastActivity,
            'fd':                    self.setFeederClientFD,
        }, {}, {})
        self.treemodel.set(i, 2, w, 3, 'client')
        self.treeview.expand_all()

    def removeFeederClient(self, feederState, state):
        for row in self.treemodel:
            if self.treemodel.get_value(row.iter, 1) == feederState:
                break
        for row in row.iterchildren():
            if self.treemodel.get_value(row.iter, 1) == state:
                break
        state, watcher = self.treemodel.get(row.iter, 1, 2)
        if watcher == self.selected:
            self.select(None)
        watcher.unwatch()
        self.treemodel.remove(row.iter)

    def setUIState(self, state):
        # will only be called when we have a widget tree
        BaseAdminGtkNode.setUIState(self, state)
        self.widget.show_all()
        for feeder in state.get('feeders'):
            self.addFeeder(state, feeder)
        sel = self.treeview.get_selection()
        if sel is not None:
            sel.select_iter(self.treemodel.get_iter_first())

    def haveWidgetTree(self):
        self.labels = {}
        self.widget = self.wtree.get_widget('feeders-widget')
        self.treeview = self.wtree.get_widget('treeview-feeders')
        self.treemodel = gtk.TreeStore(str, object, object, str)
        self.treeview.set_model(self.treemodel)
        col = gtk.TreeViewColumn('Feeder', gtk.CellRendererText(),
                                 text=0)
        self.treeview.append_column(col)
        sel = self.treeview.get_selection()
        sel.set_mode(gtk.SELECTION_SINGLE)
        def sel_changed(sel):
            model, i = sel.get_selected()
            self.select(i and model.get_value(i, 2))
            # don't show the feeder client stuff for a feeder
            if model.get_value(i, 3) == 'feeder':
                self.setFeederClientName(model.get_value(i, 1), None)
                self._table_feedclient.hide()
            else:
                parent = model.get_value(model.iter_parent(i), 1)
                self.setFeederName(parent, parent.get('feederName'))
                self._table_feedclient.show()

        sel.connect('changed', sel_changed)

        def set_label(name):
            self.labels[name] = self.wtree.get_widget('label-' + name)
            # zeroes out all value labels
            self.labels[name].set_text('')

        for type in ('feeder-name', 'eater-name',
                     'bytes-read-current', 'buffers-dropped-current',
                     'connected-since', 'connection-time',
                     'disconnected-since', 'disconnection-time',
                     'bytes-read-total', 'buffers-dropped-total',
                     'connections-total', 'last-activity'):
            set_label(type)

        self._table_connected = self.wtree.get_widget('table-current-connected')
        self._table_disconnected = self.wtree.get_widget(
            'table-current-disconnected')
        self._table_feedclient = self.wtree.get_widget('table-feedclient')
        self._table_connected.hide()
        self._table_disconnected.hide()
        self._table_feedclient.hide()
        self.wtree.get_widget('box-right').hide()

        return self.widget

class EatersAdminGtkNode(BaseAdminGtkNode):
    gladeFile = os.path.join('flumotion', 'component', 'base', 'eaters.glade')

    def __init__(self, state, admin):
        BaseAdminGtkNode.__init__(self, state, admin, title=_("Eaters"))
        # tree model is a model of id, uiState, _StateWatcher
        # tree model contains eaters
        self.treemodel = None
        self.treeview = None
        self._selected = None # the watcher of the currently selected row
        self.labels = {}
        self._lastConnect = 0
        self._lastDisconnect = 0

    def select(self, watcher):
        if self._selected:
            self._selected.hide()
        if watcher:
            self._selected = watcher
            self._selected.show()
        else:
            self._selected = None

    def _setEaterFD(self, state, value):
        if value is None:
            self._table_connected.hide()
            self._table_disconnected.show()
        else:
            self._table_disconnected.hide()
            self._table_connected.show()

    def _setEaterName(self, state, value):
        self.labels['eater-name'].set_markup(_('Eater <b>%s</b>') % value)

    def _setEaterBytesReadCurrent(self, state, value):
        txt = value and (formatStorage(value) + _('Byte')) or ''
        self.labels['bytes-read-current'].set_text(txt)
        self._updateConnectionTime()
        self._updateDisconnectionTime()

    def _setEaterConnectionItem(self, state, key, value):
        if key == 'feedId':
            self.labels['eating-from'].set_text(str(value))
        # timestamps
        elif key == 'countTimestampDiscont':
            self.labels['timestamp-discont-count-current'].set_text(str(value))
            if value > 0:
                self._expander_discont_current.show()
        elif key == 'timeTimestampDiscont':
            text = formatTimeStamp(time.localtime(value))
            self.labels['timestamp-discont-time-current'].set_text(text)
            if value is not None:
                self._vbox_timestamp_discont_current.show()
        elif key == 'lastTimestampDiscont':
            text = formatTime(value, fractional=9)
            self.labels['timestamp-discont-last-current'].set_text(text)
            if value > 0.0:
                self._vbox_timestamp_discont_current.show()
        elif key == 'totalTimestampDiscont':
            text = formatTime(value, fractional=9)
            self.labels['timestamp-discont-total-current'].set_text(text)
            if value > 0.0:
                self._vbox_timestamp_discont_current.show()
        elif key == 'timestampTimestampDiscont':
            if value is None:
                return
            text = formatTime(value, fractional=9)
            self.labels['timestamp-discont-timestamp-current'].set_text(text)
        # offsets
        elif key == 'countOffsetDiscont':
            self.labels['offset-discont-count-current'].set_text(str(value))
            if value > 0:
                self._expander_discont_current.show()
        elif key == 'timeOffsetDiscont':
            text = formatTimeStamp(time.localtime(value))
            self.labels['offset-discont-time-current'].set_text(text)
            if value is not None:
                self._vbox_offset_discont_current.show()
        elif key == 'lastOffsetDiscont':
            text = _("%d units") % value
            self.labels['offset-discont-last-current'].set_text(text)
            if value > 0:
                self._vbox_offset_discont_current.show()
        elif key == 'totalOffsetDiscont':
            text = _("%d units") % value
            self.labels['offset-discont-total-current'].set_text(text)
            if value > 0:
                self._vbox_offset_discont_current.show()
        elif key == 'offsetOffsetDiscont':
            if value is None:
                return
            text = _("%d units") % value
            self.labels['offset-discont-offset-current'].set_text(text)
            if value > 0:
                self._vbox_offset_discont_current.show()

    def _setEaterCountTimestampDiscont(self, state, value):
        if value is None:
            return
        self.labels['timestamp-discont-count-total'].set_text(str(value))
        if value > 0.0:
            self._expander_discont_total.show()

    def _setEaterTotalTimestampDiscont(self, state, value):
        if value is None:
            return
        text = formatTime(value, fractional=9)
        self.labels['timestamp-discont-total'].set_text(text)
        if value > 0.0:
            self._vbox_timestamp_discont_total.show()

    def _setEaterCountOffsetDiscont(self, state, value):
        if value is None:
            return
        self.labels['offset-discont-count-total'].set_text(str(value))
        if value != 0:
            self._expander_discont_total.show()

    def _setEaterTotalOffsetDiscont(self, state, value):
        if value is None:
            return
        text = _("%d units") % value
        self.labels['offset-discont-total'].set_text(text)
        if value != 0:
            self._vbox_offset_discont_total.show()

    def _setEaterLastConnect(self, state, value):
        if value:
            text = formatTimeStamp(time.localtime(value))
            self.labels['connected-since'].set_text(text)
            self._table_connected.show()
            self._table_disconnected.hide()
            self._lastConnect = value
            self._updateConnectionTime()

    def _setEaterTotalConnections(self, state, value):
        self.labels['connections-total'].set_text(str(value))

    # when we initially get the uiState, connection is an already set dict
    # this makes sure we handle getting that dict initially
    def _setEaterConnection(self, state, value):
        # can be called with None value due to StateWatcher
        if value is None:
            return
        for k, v in value.items():
            self._setEaterConnectionItem(state, k, v)

    # FIXME: add a timeout to update this ?
    def _updateConnectionTime(self):
        if self._lastConnect:
            text = formatTime(time.time() - self._lastConnect)
            self.labels['connection-time'].set_text(text)

    # FIXME: add a timeout to update this ?
    def _updateDisconnectionTime(self):
        if self._lastDisconnect:
            text = formatTime(time.time() - self._lastDisconnect)
            self.labels['disconnection-time'].set_text(text)

    def addEater(self, uiState, state):
        """
        @param uiState: the component's uiState
        @param state:   the eater's uiState
        """
        eaterId = state.get('eaterAlias')
        i = self.treemodel.append(None)
        self.treemodel.set(i, 0, eaterId, 1, state)
        w = _StateWatcher(state,
            {
                'fd':                    self._setEaterFD,
                'eaterAlias':            self._setEaterName,
                'lastConnect':           self._setEaterLastConnect,
                'countTimestampDiscont': self._setEaterCountTimestampDiscont,
                'totalTimestampDiscont': self._setEaterTotalTimestampDiscont,
                'countOffsetDiscont':    self._setEaterCountOffsetDiscont,
                'totalOffsetDiscont':    self._setEaterTotalOffsetDiscont,
                'totalConnections':      self._setEaterTotalConnections,
                # need to have a setter for connection to be able to show
                # it initially
                'connection':            self._setEaterConnection,
            },
            {},
            {},
            setitemers={
                'connection':           self._setEaterConnectionItem,
            },
            delitemers={
            }
        )
        self.treemodel.set(i, 2, w)

    def setUIState(self, state):
        # will only be called when we have a widget tree
        BaseAdminGtkNode.setUIState(self, state)
        #self.widget.show_all()
        for eater in state.get('eaters'):
            self.addEater(state, eater)

    def haveWidgetTree(self):
        self.labels = {}
        self.widget = self.wtree.get_widget('eaters-widget')
        self.treeview = self.wtree.get_widget('treeview-eaters')
        # tree model is a model of id, uiState, _StateWatcher
        self.treemodel = gtk.TreeStore(str, object, object)
        self.treeview.set_model(self.treemodel)
        col = gtk.TreeViewColumn('Eater', gtk.CellRendererText(),
                                 text=0)
        self.treeview.append_column(col)
        sel = self.treeview.get_selection()
        sel.set_mode(gtk.SELECTION_SINGLE)

        # get to know and set labels
        def set_label(name):
            self.labels[name] = self.wtree.get_widget('label-' + name)
            if self.labels[name] is None:
                raise KeyError(name)
            # zeroes out all value labels
            self.labels[name].set_text('')

        for type in (
            'eater-name', 'connected-since', 'connection-time',
            'eating-from', 'timestamp-discont-timestamp-current',
            'offset-discont-offset-current',
            'timestamp-discont-count-current', 'offset-discont-count-current',
            'timestamp-discont-total-current', 'offset-discont-total-current',
            'timestamp-discont-last-current',  'offset-discont-last-current',
            'timestamp-discont-time-current',  'offset-discont-time-current',
            'timestamp-discont-count-total',   'offset-discont-count-total',
            'timestamp-discont-total',         'offset-discont-total',
            'connections-total',
            ):
            set_label(type)

        # handle selection changes on the tree widget
        def sel_changed(sel):
            model, i = sel.get_selected()
            self.select(i and model.get_value(i, 2))
            self.wtree.get_widget('box-right').show()

        sel.connect('changed', sel_changed)

        # manage visibility of parts of the widget
        self._table_connected = self.wtree.get_widget('table-current-connected')
        self._table_disconnected = self.wtree.get_widget(
            'table-current-disconnected')
        self._table_eater = self.wtree.get_widget('table-eater')
        self._expander_discont_current = self.wtree.get_widget(
            'expander-discont-current')
        self._vbox_timestamp_discont_current = self.wtree.get_widget(
            'vbox-timestamp-discont-current')
        self._vbox_offset_discont_current = self.wtree.get_widget(
            'vbox-offset-discont-current')

        self._expander_discont_total = self.wtree.get_widget(
            'expander-discont-total')
        self._vbox_timestamp_discont_total = self.wtree.get_widget(
            'vbox-timestamp-discont-total')
        self._vbox_offset_discont_total = self.wtree.get_widget(
            'vbox-offset-discont-total')
        #
        # show the tree view always
        self.wtree.get_widget('scrolledwindow').show_all()

        # hide the specifics of the eater
        self._expander_discont_current.hide()
        self._table_connected.hide()
        self._table_disconnected.hide()
        self._expander_discont_total.hide()

        # show the right box only when an eater is selected
        self.wtree.get_widget('box-right').hide()

        # FIXME: do not show all;
        # hide bytes fed and buffers dropped until something is selected
        # see #575
        self.widget.show()
        return self.widget

class EffectAdminGtkNode(BaseAdminGtkNode):
    """
    I am a base class for all GTK+-based component effect Admin UI nodes.
    I am a view on a set of properties for an effect on a component.
    """
    def __init__(self, state, admin, effectName, title=None):
        """
        @param state: state of component this is a UI for
        @type  state: L{flumotion.common.planet.AdminComponentState}
        @param admin: the admin model that interfaces with the manager for us
        @type  admin: L{flumotion.admin.admin.AdminModel}
        """
        BaseAdminGtkNode.__init__(self, state, admin, title)
        self.effectName = effectName

    def effectCallRemote(self, methodName, *args, **kwargs):
        return self.admin.componentCallRemote(self.state,
            "effect", self.effectName, methodName, *args, **kwargs)

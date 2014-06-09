# -*- Mode: Python; test-case-name: flumotion.test.test_common_gstreamer -*-
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

"""gstreamer helpers
"""

from twisted.internet import defer
# moving this down causes havoc when running this file directly for some reason
from flumotion.common import errors, log

import gi
gi.require_version('Gst', '1.0')
from gi.repository import GObject, Gst

GObject.threads_init()
Gst.init(None)

__version__ = "$Rev$"


def caps_repr(caps):
    """
    Represent L{Gst.Caps} as a string.

    @rtype: string
    """
    value = caps.to_string()
    pos = value.find('streamheader')
    if pos != -1:
        return 'streamheader=<...>'
    else:
        return value


def verbose_deep_notify_cb(object, orig, pspec, component):
    """
    A default deep-notify signal handler for pipelines.
    """
    value = orig.get_property(pspec.name)
    if pspec.value_type == GObject.TYPE_BOOLEAN:
        if value:
            value = 'TRUE'
        else:
            value = 'FALSE'
        output = value
    elif pspec.value_type == Gst.Caps.__gtype__:
        output = caps_repr(value)
    else:
        output = value

    # Filters
    if pspec.name == 'active':
        return
    if pspec.name == 'caps' and output == 'None':
        return

    component.debug('%s: %s = %r', orig.get_path_string(), pspec.name, output)


def element_has_property(element, property_name):
    """
    Check if the given element has the given property.

    @rtype: boolean
    """
    try:
        element.get_property(property_name)
        return True
    except TypeError:
        return False


def element_factory_has_property(element_factory, property_name):
    """
    Check if the given element factory has the given property.

    @rtype: boolean
    """
    # FIXME: find a better way than instantiating one
    e = Gst.ElementFactory.make(element_factory, None)
    for pspec in GObject.list_properties(e):
        if pspec.name == property_name:
            return True
    return False


def element_factory_has_property_value(element_factory, property_name, value):
    """
    Check if the given element factory allows the given value
    for the given property.

    @rtype: boolean
    """
    # FIXME: find a better way than instantiating one
    e = Gst.ElementFactory.make(element_factory, None)
    try:
        e.set_property(property_name, value)
    except TypeError:
        return False

    return True


def element_factory_exists(name):
    """
    Check if the given element factory name exists.

    @rtype: boolean
    """
    registry = Gst.registry_get_default()
    factory = registry.find_feature(name, Gst.TYPE_ELEMENT_FACTORY)

    if factory:
        return True

    return False


def get_plugin_version(plugin_name):
    """
    Find the version of the given plugin.

    @rtype: tuple of (major, minor, micro, nano), or None if it could not be
            found or determined
    """
    plugin = Gst.Registry.get().find_plugin(plugin_name)

    if not plugin:
        return None

    versionTuple = tuple([int(x) for x in plugin.get_version().split('.')])
    if len(versionTuple) < 4:
        versionTuple = versionTuple + (0, )
    return versionTuple

# GstPython should have something for this, but doesn't.


def get_state_change(old, new):
    table = {(Gst.State.NULL, Gst.State.READY):
             Gst.StateChange.NULL_TO_READY,
             (Gst.State.READY, Gst.State.PAUSED):
             Gst.StateChange.READY_TO_PAUSED,
             (Gst.State.PAUSED, Gst.State.PLAYING):
             Gst.StateChange.PAUSED_TO_PLAYING,
             (Gst.State.PLAYING, Gst.State.PAUSED):
             Gst.StateChange.PLAYING_TO_PAUSED,
             (Gst.State.PAUSED, Gst.State.READY):
             Gst.StateChange.PAUSED_TO_READY,
             (Gst.State.READY, Gst.State.NULL):
             Gst.StateChange.READY_TO_NULL}
    return table.get((old, new), 0)


def flumotion_reset_event():
    ''' Helper method to create a 'flumotion-reset' event '''
    return Gst.event_new_custom(Gst.EVENT_CUSTOM_DOWNSTREAM,
                                Gst.Structure('flumotion-reset'))


def event_is_flumotion_reset(event):
    ''' Helper method to check if an event is a 'flumotion-reset' event '''
    event = event.get_event()
    if event.get_structure() is None:
        return False
    return event.get_structure().get_name() == 'flumotion-reset'


class StateChangeMonitor(dict, log.Loggable):

    def __init__(self):
        # statechange -> [ deferred ]
        dict.__init__(self)

    def add(self, statechange):
        if statechange not in self:
            self[statechange] = []

        d = defer.Deferred()
        self[statechange].append(d)

        return d

    def state_changed(self, old, new):
        self.log('state change: pipeline %s->%s',
                 old.value_nick, new.value_nick)
        change = get_state_change(old, new)
        if change in self:
            dlist = self[change]
            for d in dlist:
                d.callback(None)
            del self[change]

    def have_error(self, curstate, message):
        # if we have a state change defer that has not yet
        # fired, we should errback it
        changes = [Gst.StateChange.NULL_TO_READY,
                   Gst.StateChange.READY_TO_PAUSED,
                   Gst.StateChange.PAUSED_TO_PLAYING]

        extras = ((Gst.State.PAUSED, Gst.StateChange.PLAYING_TO_PAUSED),
                  (Gst.State.READY, Gst.StateChange.PAUSED_TO_READY),
                  (Gst.State.NULL, Gst.StateChange.READY_TO_NULL))
        for state, change in extras:
            if curstate <= state:
                changes.append(change)

        for change in changes:
            if change in self:
                self.log("We have an error, going to errback pending "
                         "state change defers")
                gerror, debug = message.parse_error()
                for d in self[change]:
                    d.errback(errors.GStreamerGstError(
                        message.src, gerror, debug))
                del self[change]

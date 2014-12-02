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

from flumotion.common import gstreamer
from flumotion.common.i18n import gettexter
from flumotion.component import feedcomponent

__version__ = "$Rev$"
T_ = gettexter()


DEFAULT_INTERVAL = 10 * Gst.SECOND


class GstKeyUnitsScheduler(Gst.Element):

    __gproperties__ = {
            'interval': (GObject.TYPE_UINT64,
            'Key Unit Interval',
            'Key Unit interval in ns',
            0, Gst.CLOCK_TIME_NONE, DEFAULT_INTERVAL,
            GObject.PARAM_READWRITE)}

    __gstmetadata__ = ('FluKeyUnitsScheduler', 'Converter',
                      'Key Units scheduler for flumotion',
                      'Flumotion Dev Team')

    _sinkpadtemplate = Gst.PadTemplate.new("sink",
                                         Gst.PadDirection.SINK,
                                         Gst.PadPresence.ALWAYS,
                                         Gst.Caps.new_any())

    _srcpadtemplate = Gst.PadTemplate.new("src",
                                         Gst.PadDirection.SRC,
                                         Gst.PadPresence.ALWAYS,
                                         Gst.Caps.new_any())

    def __init__(self):
        Gst.Element.__init__(self)
        self.sinkpad = Gst.Pad.new_from_template(self._sinkpadtemplate, "sink")
        self.sinkpad.set_chain_function_full(self.chainfunc)
        self.add_pad(self.sinkpad)

        self.srcpad = Gst.Pad.new_from_template(self._srcpadtemplate, "src")
        self.add_pad(self.srcpad)

        self._last_ts = 0L
        self._count = 0
        self.interval = DEFAULT_INTERVAL

    def _send_event(self, timestamp):
        clock = self.get_clock()
        if clock is not None:
            running_time = clock.get_time() - self.get_base_time()
        else:
            running_time = 0
        s = Gst.Structure("GstForceKeyUnit")
        s.set_value('timestamp', timestamp, 'uint64')
        s.set_value('stream-time', timestamp, 'uint64')
        s.set_value('running-time', running_time, 'uint64')
        s.set_value('all-headers', True)
        s.set_value('count', self._count)
        return self.srcpad.push_event(
            Gst.event_new_custom(Gst.EVENT_CUSTOM_DOWNSTREAM, s))

    def chainfunc(self, pad, buf):
        if self.interval == 0 or buf.timestamp == Gst.CLOCK_TIME_NONE:
            pass
        elif self._last_ts == 0 or \
                buf.timestamp >= self._last_ts + self.interval:
            self._count += 1
            self._last_ts = buf.timestamp
            if not self._send_event(buf.timestamp):
                self.warning("Error sending GstForceKeyUnit event")
        return self.srcpad.push(buf)

    def do_change_state(self, transition):
        if transition == Gst.StateChange.PAUSED_TO_READY:
            self._last_ts = 0L
            self._count = 0
        return Gst.Element.do_change_state(self, transition)

    def do_set_property(self, property, value):
        if property.name == 'interval':
            self.interval = value
        else:
            raise AttributeError('unknown property %s' % property.name)

    def do_get_property(self, property):
        if property.name == 'interval':
            return self.interval
        raise AttributeError('unknown property %s' % property.name)


class KeyUnitsScheduler(feedcomponent.PostProcEffect):
    """
    I can be added after a raw video source to schedule GstForceKeyUnit
    event, used to synchronize downstream elements, like encoders or
    fragmenters.
    """
    logCategory = "kuscheduler-effect"

    def __init__(self, name, sourcePad, pipeline, interval):
        """
        @param element:     the video source element on which the post
                            processing effect will be added
        @param sourcePad:   source pad used for linking the effect
        @param pipeline:    the pipeline of the element
        @param interval:    interval between GstForceKeyUnit events in ns
        """
        feedcomponent.PostProcEffect.__init__(self, name, sourcePad,
            self.get_kuscheduler(interval), pipeline)

    def get_kuscheduler(self, interval):
        if not gstreamer.element_factory_exists('keyunitsscheduler'):
            register()

        kubin = Gst.parse_bin_from_description('keyunitsscheduler interval=%s '
                'name=scheduler' % interval, True)
        self._kuscheduler = kubin.get_by_name('scheduler')
        return kubin

    def effect_setInterval(self, interval):
        self._kuscheduler.set_property('interval', interval)
        return interval

    def effect_getInterval(self):
        return self._kuscheduler.get_property('interval')


def register():

    def plugin_init(plugin, userarg):
        name = plugin.get_name()
        pluginType = GObject.type_register(userarg)
        Gst.Element.register(plugin, name, Gst.Rank.MARGINAL, pluginType)
        return True

    version = Gst.version()

    Gst.Plugin.register_static_full(
        version[0], # GST_VERSION_MAJOR
        version[1], # GST_VERSION_MINOR
        'keyunitsscheduler',
        'key units scheduler plugin',
        plugin_init,
        '12.06',
        'LGPL',
        'keyunitsscheduler',
        'keyunitsscheduler',
        '',
        GstKeyUnitsScheduler,
    )

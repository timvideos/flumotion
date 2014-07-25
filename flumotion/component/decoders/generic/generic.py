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

from gi.repository import Gst
from gi.repository import GObject
import threading

from flumotion.component import decodercomponent as dc
from flumotion.common import messages, gstreamer
from flumotion.common.i18n import N_, gettexter

T_ = gettexter()

__version__ = "$Rev: 7162 $"

BASIC_AUDIO_CAPS = "audio/x-raw;audio/x-raw"
BASIC_VIDEO_CAPS = "video/x-raw;video/x-raw"

# FIXME: The GstAutoplugSelectResult enum has no bindings in gst-python.
# Replace this when the enum is exposed in the bindings.

GST_AUTOPLUG_SELECT_TRY = 0
GST_AUTOPLUG_SELECT_SKIP = 2


class FeederInfo(object):

    def __init__(self, name, caps, linked=False):
        self.name = name
        self.caps = caps


class SyncKeeper(Gst.Element):
    __gstmetadata__ = ('SyncKeeper', 'Generic',
                      'Retimestamp the output to be contiguous and maintain '
                      'the sync', 'Xavier Queralt')
    _audiosink = Gst.PadTemplate.new("audio-in",
                                 Gst.PadDirection.SINK,
                                 Gst.PadPresence.ALWAYS,
                                 Gst.Caps.from_string(BASIC_AUDIO_CAPS))
    _videosink = Gst.PadTemplate.new("video-in",
                                 Gst.PadDirection.SINK,
                                 Gst.PadPresence.ALWAYS,
                                 Gst.Caps.from_string(BASIC_VIDEO_CAPS))
    _audiosrc = Gst.PadTemplate.new("audio-out",
                                Gst.PadDirection.SRC,
                                Gst.PadPresence.ALWAYS,
                                Gst.Caps.from_string(BASIC_AUDIO_CAPS))
    _videosrc = Gst.PadTemplate.new("video-out",
                                Gst.PadDirection.SRC,
                                Gst.PadPresence.ALWAYS,
                                Gst.Caps.from_string(BASIC_VIDEO_CAPS))

    def __init__(self):
        Gst.Element.__init__(self)

        # create source pads
        self.audiosrc = Gst.Pad.new_from_template(self._audiosrc, "audio-out")
        self.add_pad(self.audiosrc)
        self.videosrc = Gst.Pad.new_from_template(self._videosrc, "video-out")
        self.add_pad(self.videosrc)

        # create the sink pads and set the chain and event function
        self.audiosink = Gst.Pad.new_from_template(self._audiosink, "audio-in")
        self.audiosink.set_chain_function(lambda pad, buffer:
            self.chainfunc(pad, buffer, self.audiosrc))
        self.audiosink.set_event_function(lambda pad, buffer:
            self.eventfunc(pad, buffer, self.audiosrc))
        self.add_pad(self.audiosink)
        self.videosink = Gst.Pad.new_from_template(self._videosink, "video-in")
        self.videosink.set_chain_function(lambda pad, buffer:
            self.chainfunc(pad, buffer, self.videosrc))
        self.videosink.set_event_function(lambda pad, buffer:
            self.eventfunc(pad, buffer, self.videosrc))
        self.add_pad(self.videosink)

        # all this variables need to be protected with a lock!!!
        self._lock = threading.Lock()
        self._totalTime = 0L
        self._syncTimestamp = 0L
        self._syncOffset = 0L
        self._resetReceived = True
        self._sendNewSegment = True

    def _send_new_segment(self):
        for pad in [self.videosrc, self.audiosrc]:
            pad.push_event(
                Gst.Event.new_segment(True, 1.0, Gst.Format.TIME,
                                          self._syncTimestamp, -1, 0))
        self._sendNewSegment = False

    def _update_sync_point(self, start, position):
        # Only update the sync point if we haven't received any buffer
        # (totalTime == 0) or we received a reset
        if not self._totalTime and not self._resetReceived:
            return
        self._syncTimestamp = self._totalTime
        if position >= start:
            self._syncOffset = start + (position - start)
        else:
            self._syncOffset = start
        self._resetReceived = False
        self.info("Update sync point to % r, offset to %r" %
            (Gst.TIME_ARGS(self._syncTimestamp),
            (Gst.TIME_ARGS(self._syncOffset))))

    def chainfunc(self, pad, buf, srcpad):
        self.log("Input %s timestamp: %s, %s" %
            (srcpad is self.audiosrc and 'audio' or 'video',
            Gst.TIME_ARGS(buf.pts),
            Gst.TIME_ARGS(buf.duration)))

        if not self._sendNewSegment:
            self._send_new_segment()

        try:
            self._lock.acquire()
            # Discard buffers outside the configured segment
            if buf.pts < self._syncOffset:
                self.warning("Could not clip buffer to segment")
                return Gst.FlowReturn.OK
            if buf.pts == Gst.CLOCK_TIME_NONE:
                return Gst.FlowReturn.OK
            # Get the input stream time of the buffer
            buf.pts -= self._syncOffset
            # Set the accumulated stream time
            buf.pts += self._syncTimestamp
            duration = 0
            if buf.duration != Gst.CLOCK_TIME_NONE:
                duration = buf.duration
            self._totalTime = max(buf.pts + duration, self._totalTime)

            self.log("Output %s timestamp: %s, %s" %
                (srcpad is self.audiosrc and 'audio' or 'video',
                Gst.TIME_ARGS(buf.pts),
                Gst.TIME_ARGS(buf.duration)))
        finally:
            self._lock.release()

        srcpad.push(buf)
        return Gst.FlowReturn.OK

    def eventfunc(self, pad, event, srcpad):
        self.debug("Received event %r from %s" % (event, event.src))
        try:
            self._lock.acquire()
            if event.type == Gst.EventType.SEGMENT:
                u, r, f, start, s, position = event.parse_new_segment()
                self._update_sync_point(start, position)
            if gstreamer.event_is_flumotion_reset(event):
                self._resetReceived = True
                self._send_new_segment = True
        finally:
            self._lock.release()

        # forward all the events except the new segment events
        if event.type != Gst.EventType.SEGMENT:
            return srcpad.push_event(event)
        return True

def plugin_init(plugin, userarg):
    name = plugin.get_name()
    pluginType = GObject.type_register(userarg)
    Gst.Element.register(plugin, name, Gst.Rank.MARGINAL, pluginType)
    return True

version = Gst.version()

Gst.Plugin.register_static_full(
    version[0],  # GST_VERSION_MAJOR
    version[1],  # GST_VERSION_MINOR
    'synckeeper',
    'sync keeper plugin',
    plugin_init,
    '12.06',
    'LGPL',
    'synckeeper',
    'synckeeper',
    '',
    SyncKeeper,
)


class GenericDecoder(dc.DecoderComponent):
    """
    Generic decoder component using decodebin.

    It listen to the custom gstreamer event flumotion-reset,
    and reset the decoding pipeline by removing the old one
    and creating a new one.

    Sub-classes must override _get_feeders_info() and return
    a list of FeederInfo instances that describe the decoder
    output.

    When reset, if the new decoded pads do not match the
    previously negotiated caps, feeder will not be connected,
    and the decoder will go sad.
    """

    logCategory = "gen-decoder"
    feeder_tmpl = ("identity name=%(ename)s single-segment=true "
                   "silent=true ! %(caps)s ! @feeder:%(pad)s@")

    ### Public Methods ###

    def init(self):
        self._feeders_info = None # {FEEDER_NAME: FeederInfo}

    def get_pipeline_string(self, properties):
        # Retrieve feeder info and build a dict out of it
        finfo = self._get_feeders_info()
        assert finfo, "No feeder info specified"
        self._feeders_info = dict([(i.name, i) for i in finfo])

        pipeline_parts = [self._get_base_pipeline_string()]

        for i in self._feeders_info.values():
            ename = self._get_output_element_name(i.name)
            pipeline_parts.append(
                self.feeder_tmpl % dict(ename=ename, caps=i.caps, pad=i.name))

        pipeline_str = " ".join(pipeline_parts)
        self.log("Decoder pipeline: %s", pipeline_str)

        self._blacklist = properties.get('blacklist', [])

        return pipeline_str

    def configure_pipeline(self, pipeline, properties):
        dc.DecoderComponent.configure_pipeline(self, pipeline,
                                               properties)

        decoder = self.pipeline.get_by_name("decoder")
        decoder.connect('autoplug-select', self._autoplug_select_cb)

    ### Protected Methods ##

    def _get_base_pipeline_string(self):
        return 'decodebin name=decoder'

    def _get_feeders_info(self):
        """
        Must be overridden to returns a tuple of FeederInfo.
        """
        return None

    ### Private Methods ###

    def _get_output_element_name(self, feed_name):
        return "%s-output" % feed_name

    ### Callbacks ###

    def _autoplug_select_cb(self, decoder, pad, caps, factory):
        if factory.get_name() in self._blacklist:
            self.log("Skipping element %s because it's in the blacklist",
                     factory.get_name())
            return GST_AUTOPLUG_SELECT_SKIP
        return GST_AUTOPLUG_SELECT_TRY


class SingleGenericDecoder(GenericDecoder):

    logCategory = "sgen-decoder"

    _caps_lookup = {'audio': BASIC_AUDIO_CAPS,
                    'video': BASIC_VIDEO_CAPS}

    def init(self):
        self._media_type = None

    def check_properties(self, properties, addMessage):
        media_type = properties.get("media-type")
        if media_type not in ["audio", "video"]:
            msg = 'Property media-type can only be "audio" or "video"'
            m = messages.Error(T_(N_(msg)), mid="error-decoder-media-type")
            addMessage(m)
        else:
            self._media_type = media_type

    def _get_feeders_info(self):
        caps = self._caps_lookup[self._media_type]
        return FeederInfo('default', caps),


class AVGenericDecoder(GenericDecoder):

    logCategory = "avgen-decoder"
    feeder_tmpl = ("identity name=%(ename)s silent=true ! %(caps)s ! "
                   "sync.%(pad)s-in sync.%(pad)s-out ! @feeder:%(pad)s@")

    def _get_feeders_info(self):
        return (FeederInfo('audio', BASIC_AUDIO_CAPS),
                FeederInfo('video', BASIC_VIDEO_CAPS))

    def _get_base_pipeline_string(self):
        return 'decodebin name=decoder synckeeper name=sync'

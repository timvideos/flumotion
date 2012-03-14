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

from flumotion.component import feedcomponent

__all__ = ['Consumer']
__version__ = "$Rev: 7162 $"


class JustinTV(feedcomponent.MultiInputParseLaunchComponent):
    LINK_MUXER=False

    def get_pipeline_string(self, properties):
        self._justintv_user = properties['justintv-user']
        self._justintv_key = properties['justintv-key']

        assert 'video' in self.eaters
        assert 'audio' in self.eaters

        # These settings from from
        #   http://apiwiki.justin.tv/mediawiki/index.php/VLC_Broadcasting_API

        #video/x-raw-yuv, width= !
        #x264{keyint=60,idrint=2},vcodec=h264,vb=300
        videopipe = """\
@ eater:video @ !
videoscale !
x264enc bframes=0 key-int-max=2 bitrate=300 !
muxer.
"""
        # acodec=mp4a,ab=32,channels=2,samplerate=2205
        audiopipe = """\
@ eater:audio @ !
audioconvert !
audioresample !
audio/x-raw-int,channels=1,samplerate=44100 !
lamemp3enc bitrate=64 mono=1 target=bitrate cbr=1 !
muxer.
"""
        # gst-launch-0.10 -v videotestsrc ! ffenc_flv ! flvmux ! rtmpsink location='rtmp://live.justin.tv/app/live_22076196_raZAJ55hsNU4Z9LN130N1GL71KJok6 live=1'
        outputpipe = """\
flvmux name=muxer streamable=true !
rtmpsink location="rtmp://live.justin.tv/app/%s live=1"
""" % (self._justintv_key)

        return videopipe + "\n\n" + audiopipe + "\n\n" + outputpipe

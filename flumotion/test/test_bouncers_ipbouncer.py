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

from twisted.internet import defer

from flumotion.common import testsuite

from flumotion.common import keycards
from flumotion.common.planet import moods
from flumotion.component.bouncers import ipbouncer

from flumotion.test import bouncertest


class TestIPBouncer(bouncertest.BouncerTestHelper):

    bouncerClass = ipbouncer.IPBouncer

    def test_trivial(self):
        bouncer = self.get_bouncer({})
        keycard = keycards.KeycardGeneric()
        keycard.username = 'user'
        keycard.password = 'test'
        keycard.address = '62.121.66.134'
        d = self.check_auth(keycard, bouncer, False)
        return self.stop_bouncer(bouncer, d)

    def test_trivial_allow_correct(self):
        bouncer = self.get_bouncer({'allow': ['62.121.66.134/32']})
        keycard = keycards.KeycardGeneric()
        keycard.username = 'user'
        keycard.password = 'test'
        keycard.address = '62.121.66.134'
        d = self.check_auth(keycard, bouncer, True)
        return self.stop_bouncer(bouncer, d)

    def test_trivial_allow_deny(self):
        bouncer = self.get_bouncer({'allow': ['62.121.66.134/32']})
        keycard = keycards.KeycardGeneric()
        keycard.username = 'user'
        keycard.password = 'test'
        keycard.address = '62.121.66.135'
        d = self.check_auth(keycard, bouncer, False)
        return self.stop_bouncer(bouncer, d)

    def test_trivial_deny(self):
        bouncer = self.get_bouncer({'deny': ['62.121.66.134/32']})
        keycard = keycards.KeycardGeneric()
        keycard.username = 'user'
        keycard.password = 'test'
        keycard.address = '62.121.66.134'
        d = self.check_auth(keycard, bouncer, False)
        return self.stop_bouncer(bouncer, d)

    def test_trivial_deny_allow_default(self):
        bouncer = self.get_bouncer({'deny-default': False,
                                     'deny': ['62.121.66.134/32']})
        keycard = keycards.KeycardGeneric()
        keycard.username = 'user'
        keycard.password = 'test'
        keycard.address = '62.121.66.134'
        d = self.check_auth(keycard, bouncer, False)

        keycard = keycards.KeycardGeneric()
        keycard.username = 'user'
        keycard.password = 'test'
        keycard.address = '62.121.66.135'
        d.addCallback(lambda _: self.check_auth(keycard, bouncer, True))
        return self.stop_bouncer(bouncer, d)

    def test_both_allow_and_deny(self):
        bouncer = self.get_bouncer({'allow': ['62.121.66.134/32'],
                                     'deny': ['62.121.66.135/32']})
        keycard = keycards.KeycardGeneric()
        keycard.username = 'user'
        keycard.password = 'test'
        keycard.address = '62.121.66.135'
        d = self.check_auth(keycard, bouncer, False)

        keycard = keycards.KeycardGeneric()
        keycard.username = 'user'
        keycard.password = 'test'
        keycard.address = '62.121.66.134'
        d.addCallback(lambda _: self.check_auth(keycard, bouncer, True))

        keycard = keycards.KeycardGeneric()
        keycard.username = 'user'
        keycard.password = 'test'
        keycard.address = '62.121.66.133'
        d.addCallback(lambda _: self.check_auth(keycard, bouncer, False))
        return self.stop_bouncer(bouncer, d)

    def test_both_allow_and_deny_allow_default(self):
        bouncer = self.get_bouncer({'deny-default': False,
                                     'allow': ['62.121.66.134/32'],
                                     'deny': ['62.121.66.135/32']})
        keycard = keycards.KeycardGeneric()
        keycard.username = 'user'
        keycard.password = 'test'
        keycard.address = '62.121.66.135'
        d = self.check_auth(keycard, bouncer, False)

        keycard = keycards.KeycardGeneric()
        keycard.username = 'user'
        keycard.password = 'test'
        keycard.address = '62.121.66.134'
        d.addCallback(lambda _: self.check_auth(keycard, bouncer, True))

        keycard = keycards.KeycardGeneric()
        keycard.username = 'user'
        keycard.password = 'test'
        keycard.address = '62.121.66.133'
        d.addCallback(lambda _: self.check_auth(keycard, bouncer, True))
        return self.stop_bouncer(bouncer, d)

    def test_multiple_allows_and_denies(self):
        bouncer = self.get_bouncer({'allow': ['62.121.66.134/32',
                                               '62.121.66.133/32'],
                                     'deny': ['62.121.66.135/32',
                                              '62.121.66.136/32']})
        keycard = keycards.KeycardGeneric()
        keycard.username = 'user'
        keycard.password = 'test'
        keycard.address = '62.121.66.136'
        d = self.check_auth(keycard, bouncer, False)

        keycard = keycards.KeycardGeneric()
        keycard.username = 'user'
        keycard.password = 'test'
        keycard.address = '62.121.66.133'
        d.addCallback(lambda _: self.check_auth(keycard, bouncer, True))

        keycard = keycards.KeycardGeneric()
        keycard.username = 'user'
        keycard.password = 'test'
        keycard.address = '62.121.66.137'
        d.addCallback(lambda _: self.check_auth(keycard, bouncer, False))
        return self.stop_bouncer(bouncer, d)

    def test_trivial_subnet_allow(self):
        bouncer = self.get_bouncer({'allow': ['62.121.66.0/24']})
        keycard = keycards.KeycardGeneric()
        keycard.username = 'user'
        keycard.password = 'test'
        keycard.address = '62.121.66.134'
        d = self.check_auth(keycard, bouncer, True)

        keycard = keycards.KeycardGeneric()
        keycard.username = 'user'
        keycard.password = 'test'
        keycard.address = '62.121.66.3'
        d.addCallback(lambda _: self.check_auth(keycard, bouncer, True))

        keycard = keycards.KeycardGeneric()
        keycard.username = 'user'
        keycard.password = 'test'
        keycard.address = '62.121.66.253'
        d.addCallback(lambda _: self.check_auth(keycard, bouncer, True))

        keycard = keycards.KeycardGeneric()
        keycard.username = 'user'
        keycard.password = 'test'
        keycard.address = '62.121.65.12'
        d.addCallback(lambda _: self.check_auth(keycard, bouncer, False))
        return self.stop_bouncer(bouncer, d)

    def test_trivial_subnet_deny(self):
        bouncer = self.get_bouncer({'deny': ['62.121.66.0/24']})
        keycard = keycards.KeycardGeneric()
        keycard.username = 'user'
        keycard.password = 'test'
        keycard.address = '62.121.66.134'
        d = self.check_auth(keycard, bouncer, False)

        keycard = keycards.KeycardGeneric()
        keycard.username = 'user'
        keycard.password = 'test'
        keycard.address = '62.121.66.3'
        d.addCallback(lambda _: self.check_auth(keycard, bouncer, False))
        return self.stop_bouncer(bouncer, d)

    def test_subnet_allow_and_deny(self):
        bouncer = self.get_bouncer({'deny': ['62.121.66.0/24'],
                                     'allow': ['62.121.0.0/16',
                                               '62.122.66.134/32']})
        keycard = keycards.KeycardGeneric()
        keycard.username = 'user'
        keycard.password = 'test'
        keycard.address = '62.121.66.134'

        d = self.check_auth(keycard, bouncer, False)

        keycard = keycards.KeycardGeneric()
        keycard.username = 'user'
        keycard.password = 'test'
        keycard.address = '62.121.65.134'
        d.addCallback(lambda _: self.check_auth(keycard, bouncer, True))

        keycard = keycards.KeycardGeneric()
        keycard.username = 'user'
        keycard.password = 'test'
        keycard.address = '62.122.66.134'
        d.addCallback(lambda _: self.check_auth(keycard, bouncer, True))

        keycard = keycards.KeycardGeneric()
        keycard.username = 'user'
        keycard.password = 'test'
        keycard.address = '62.123.66.134'
        d.addCallback(lambda _: self.check_auth(keycard, bouncer, False))
        return self.stop_bouncer(bouncer, d)

    def test_subnet_allow_and_deny_allow_default(self):
        bouncer = self.get_bouncer({'deny-default': False,
                                     'deny': ['62.121.0.0/16',
                                              '62.122.66.0/24'],
                                     'allow': ['62.121.66.134/32',
                                               '62.122.66.134/32']})
        keycard = keycards.KeycardGeneric()
        keycard.username = 'user'
        keycard.password = 'test'
        keycard.address = '62.121.66.134'
        d = self.check_auth(keycard, bouncer, True)

        keycard = keycards.KeycardGeneric()
        keycard.username = 'user'
        keycard.password = 'test'
        keycard.address = '62.121.66.135'
        d.addCallback(lambda _: self.check_auth(keycard, bouncer, False))

        keycard = keycards.KeycardGeneric()
        keycard.username = 'user'
        keycard.password = 'test'
        keycard.address = '62.122.66.135'
        d.addCallback(lambda _: self.check_auth(keycard, bouncer, False))

        keycard = keycards.KeycardGeneric()
        keycard.username = 'user'
        keycard.password = 'test'
        keycard.address = '62.122.66.134'
        d.addCallback(lambda _: self.check_auth(keycard, bouncer, True))

        keycard = keycards.KeycardGeneric()
        keycard.username = 'user'
        keycard.password = 'test'
        keycard.address = '62.123.66.134'
        d.addCallback(lambda _: self.check_auth(keycard, bouncer, True))
        return self.stop_bouncer(bouncer, d)

    def test_no_ip(self):
        bouncer = self.get_bouncer({'deny': ['62.121.66.134/32']})
        keycard = keycards.KeycardGeneric()
        keycard.username = 'user'
        keycard.password = 'test'
        keycard.address = None
        d = self.check_auth(keycard, bouncer, False)
        return self.stop_bouncer(bouncer, d)

    def test_wrong_specification(self):
        # the 'deny' property should be a subnet, not a single IP
        bouncer = self.get_bouncer({'deny': ['62.121.66.134']})
        self.assertEquals(bouncer.getMood(), moods.sad.value)
        return self.stop_bouncer(bouncer, defer.succeed(None))

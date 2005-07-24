# -*- Mode: Python -*-
# vi:si:et:sw=4:sts=4:ts=4
#
# Flumotion - a streaming media server
# Copyright (C) 2004,2005 Fluendo, S.L. (www.fluendo.com). All rights reserved.

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

from flumotion.component.base.admin_gtk import BaseAdminGtk
from flumotion.component.effects.colorbalance.admin_gtk import ColorbalanceAdminGtkNode

class WebcamAdminGtk(BaseAdminGtk):
    def setup(self):
        self._nodes = {}
        colorbalance = ColorbalanceAdminGtkNode(self.state, self.admin,
                                                'outputColorbalance')
        self._nodes['Colorbalance'] = colorbalance

    def getNodes(self):
        return self._nodes

    def component_effectPropertyChanged(self, effectName, propertyName, value):
        self.debug("effect %s has property %s changed to %r" % (
            effectName, propertyName, value))

        if not effectName == "outputColorbalance":
            self.warning("Unknown effect '%s'" % effectName)
            return
            
        cb = self._nodes['Colorbalance']
        cb.propertyChanged(propertyName, value)

GUIClass = WebcamAdminGtk

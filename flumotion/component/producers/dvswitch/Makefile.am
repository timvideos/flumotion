include $(top_srcdir)/common/python.mk

componentdir = $(libdir)/flumotion/python/flumotion/component/producers/dvswitch
component_DATA = 		\
	dvswitch.xml

component_PYTHON = 		\
	__init__.py 		\
	admin_gtk.py		\
	dvswitch.py

clean-local:
	rm -rf *.pyc *.pyo

EXTRA_DIST = $(component_DATA)

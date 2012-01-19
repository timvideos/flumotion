include $(top_srcdir)/common/python.mk

componentdir = $(libdir)/flumotion/python/flumotion/component/producers/dvsource
component_DATA = 		\
	dvsource.xml

component_PYTHON = 		\
	__init__.py 		\
	admin_gtk.py		\
	dvsource.py

clean-local:
	rm -rf *.pyc *.pyo

EXTRA_DIST = $(component_DATA)

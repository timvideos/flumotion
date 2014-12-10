Flumotion - Your streaming media server
=======================================

[![Build Status](https://travis-ci.org/aps-sids/flumotion-orig.svg?branch=porting-to-gst1.0)](https://travis-ci.org/aps-sids/flumotion-orig)

Flumotion is a streaming media server based on GStreamer and Twisted.

This is the first public development series of **Flumotion ported to Gstreamer 1.x API**.
It is still a **work in progress** and will probably still contain bugs, be difficult to install (since some parts still need to be ported), and cause you some headaches.

On the other hand, when it works and you are capturing your Firewire camera
on one machine, encoding to Theora on a second (with an overlay, of course),
encoding the audio to Vorbis on a third, muxing to Ogg on a fourth, and then
streaming both audio and video from a fifth, audio only from a sixth,
video only from a seventh, and capturing all three streams to disk from
an eighth, you feel very good about yourself.

And you also have too many computers.

Requirements
------------

* Gstreamer 1.2.4 or higher
* Gstreamer plugins - good, bad and ugly
* Python bindings GObject Introspection Libraries
* Twisted 13 or higher
* and some other python packages

**Note:** You might have to use Gstreamer Developers PPA to get the latest packages

To install system requirements on Ubuntu, run follow commands:

```bash
$ sudo add-apt-repository ppa:gstreamer-developers/ppa
$ sudo apt-get update
$ sudo apt-get install libtool autopoint autoconf libxml-parser-perl python-gi python-gobject-dev python-gst-1.0 gir1.2-gstreamer-1.0 gir1.2-gst-plugins-base-1.0 libglib2.0-dev gir1.2-glib-2.0 libgirepository1.0-dev libglib2.0-0 gir1.2-gtk-3 pkg-config libglib2.0-dev liborc-0.4-dev python-twisted python-pyparsing python-kiwi python-dateutil

# we can't use latest python-icalendar till a few things are fixed

$ sudo pip install icalendar==2.2
```

And depending on what codecs you want to use:

* libvorbis 1.0.1 or higher
* libogg 1.1 or higher
* libtheora 1.0alpha3 or higher

And if you want to build documentation:

* epydoc

And if you want support for java applets:

* cortado

Quick Start
-----------

```bash
# Build source
$ ./autogen.sh
$ make

# To run the tests
$ ./run_tests.sh

# in terminal 1
$ ./env bash
$ flumotion-manager -v -T tcp test_config.xml

# in terminal 2
$ ./env bash
$ flumotion-worker -v -T tcp -u user -p test

# in terminal 3
$ gst-launch playbin2 uri=http://localhost:8800/ogg-audio-video/
```

Some systems may not have `gst-launch`, but only `gst-launch-0.10` or `gst-launch-1.0`. In that case you can substitute either of those commands.

Alternatively, you can use any theora-enabled network player or web browser to see the stream.

```bash
# in terminal 4
$ for a in `seq 1 9`; do ( flumotion-tester http://localhost:8800/ogg-audio-video/ & ); done
```

This will throw 9 processes with 100 clients each at the server.  Hopefully, all of them will return success at the end of their run!

We use 900 clients rather than a nice round number such as 1000 because, with a standard unix system, you'll usually be limited to slightly under 1000 clients by default due to limits on open file descriptors (each client requires a file descriptor). This limit is changeable, but it's simpler to just test with slightly fewer clients.

Issues
------

Take a look at the Github issues. Please create any new issues you encounter.

Hacking
-------

The user manual is available [here](http://www.flumotion.net/doc/flumotion/manual/en/trunk/html/), but it's probably outdated since currently there is no admin GUI to work with. Still, it might be helpful if you are new to Flumotion.

The developer documentation is available [here](https://code.flumotion.com/trac/wiki/Documentation/DeveloperIntroduction). More information will be added as the work progresses.

Contributing
------------

The project had been quite dead for a while. This port was done as a [GSoC 2014](https://www.google-melange.com/gsoc/homepage/google/gsoc2014) project under [TimVideos](http://code.timvideos.us/).

You can subscribe to the official development list. Information is at
http://lists.fluendo.com/mailman/listinfo/flumotion-devel

You can visit us on IRC: [#fluendo](irc://irc.freenode.net/#fluendo) and [#timvideos](irc://irc.freenode.net/#timvideos) on irc.freenode.org

You can visit our trac installation for the Wiki, source browsing and
ticket tracking:
https://core.fluendo.com/flumotion/trac

Security
--------

Read the security chapter in the aforementioned manual to get started.

Flumotion uses SSL transport by default.  For this you need a PEM certificate
file.  For security reasons you should generate this yourself when installing
from source.

The sample configuration file for the manager contains some htpasswd-style
crypted credentials, for a user named "user" and a password "test".  Use
these only for testing; make sure you change them before putting Flumotion
into production.

The sample configuration also only allows localhost connections, to make
sure you change the configuration before moving it into production.
Remove the host entry from the sample planet.xml file to allow other hosts
to connect.

Licence
-------

This version of the Flumotion Streaming Server is licensed under the the
terms of the GNU Lesser General Public License version 2.1 as published
by the Free Software Foundation. See LICENSE.LGPL

If the conditions of this licensing strategy are not clear to you, please
contact Thomas Vander Stichele (thomas@fluendo.com).

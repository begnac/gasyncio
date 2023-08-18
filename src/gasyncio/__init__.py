# coding: utf-8
#
# A minimalistic asyncio event loop based on the GLib main event loop
#
# Copyright (C) 2021 Itaï BEN YAACOV
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301  USA


__version__ = '0.1.1'


from .gevents import GAsyncIOEventLoop, GAsyncIOEventLoopPolicy, start_slave_loop, stop_slave_loop


__all__ = ['GAsyncIOEventLoop', 'GAsyncIOEventLoopPolicy', 'start_slave_loop', 'stop_slave_loop']

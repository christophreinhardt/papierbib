"""Calibre wrapper: GUI imports are deliberately deferred."""
from calibre.customize import InterfaceActionBase


class PapierbibliothekPlugin(InterfaceActionBase):
    name = 'Papierbibliothek'
    description = 'Papierbücher anhand von Regalfotos erfassen und exportieren'
    supported_platforms = ['windows', 'osx', 'linux']
    author = 'Christoph Reinhardt'
    version = (0, 6, 12)
    minimum_calibre_version = (7, 0, 0)
    actual_plugin = 'calibre_plugins.papierbibliothek.calibre_plugin.action:PapierbibliothekAction'

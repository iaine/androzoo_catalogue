import webview
from androzoo import androzoo

"""
An example of serverless app architecture
"""


class Api:
    def searchCatalogue(self, title):
        print(f'Added item {title}')


    def toggleFullscreen(self):
        webview.windows[0].toggle_fullscreen()


if __name__ == '__main__':
    api = Api()
    webview.create_window('AZ Catalogue', 'assets/index.html', js_api=api, min_size=(600, 450))
    webview.start(ssl=True)

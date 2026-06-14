'''
pywebview desktop front-end for the AndroZoo catalogue search.

The catalogue scan can take several minutes, so searches run on a
background thread and the result is pushed back to the page via
`onSearchDone` / `onSearchError`. The UI never blocks.
'''
import threading
import traceback

import webview

from androzoo import AndroZoo


class Api:
    def __init__(self):
        self.az = AndroZoo()

    def search_catalogue(self, apk_name="", store="", start="", end=""):
        '''
        Kick off a search on a background thread and return immediately.
        Results arrive in the page through evaluate_js callbacks.
        '''
        def work():
            try:
                info = self.az.search(apk_name, store, start, end)
                self._emit("onSearchDone", info)
            except Exception as e:  # noqa: BLE001 - surface message to UI
                traceback.print_exc()
                self._emit("onSearchError", {"message": str(e)})

        threading.Thread(target=work, daemon=True).start()
        return {"status": "running"}

    def toggle_fullscreen(self):
        webview.windows[0].toggle_fullscreen()

    def _emit(self, fn, payload):
        '''Call a JS function on the page with a JSON payload.'''
        import json
        js = "{}({})".format(fn, json.dumps(payload))
        webview.windows[0].evaluate_js(js)


if __name__ == "__main__":
    api = Api()
    webview.create_window(
        "AZ Catalogue",
        "assets/index.html",
        js_api=api,
        min_size=(700, 500),
    )
    webview.start()

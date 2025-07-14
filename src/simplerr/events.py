import logging

logger = logging.getLogger(__name__)


class WebEvents(object):
    """Web Request object, extends Request object.  """

    def __init__(self):
        self.pre_request = []
        self.post_request = []

    # Pre-request subscription
    def on_pre_response(self, fn):
        self.pre_request.append(fn)

    def off_pre_response(self, fn):
        self.pre_request.remove(fn)

    def fire_pre_response(self, request):
        for fn in self.pre_request:
            try:
                fn(request)
            except Exception as e:
                logger.error(f"Error in pre-response event: {e}")
                raise

    # Post-Request subscription management
    def on_post_response(self, fn):
        self.post_request.append(fn)

    def off_post_response(self, fn):
        self.post_request.remove(fn)

    def fire_post_response(self, request, response, exc):
        for fn in self.post_request:
            try:
                fn(request, response, exc)
            except Exception as e:
                logger.error(f"Error in post-response event: {e}")
                raise

from authlib.integrations.base_client import FrameworkIntegration
class SimplerrIntegration(FrameworkIntegration):
    @staticmethod
    def load_config(oauth, name, params):
        if not oauth.config:
            return {}

        rv = {}
        for k in params:
            conf_key = '{}_{}'.format(name, k).upper()
            v = oauth.config.get(conf_key, None)
            if v is not None:
                rv[k] = v
        return rv

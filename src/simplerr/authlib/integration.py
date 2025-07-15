from collections.abc import Callable

from authlib.integrations.base_client import FrameworkIntegration
class SimplerrIntegration(FrameworkIntegration):
    @staticmethod
    def load_config(oauth, name, params):
        if not oauth.config:
            return {}

        if isinstance(oauth.config, Callable):
            result = oauth.config(oauth, name, params)
            if result is None:
                raise RuntimeError('config factory must return a value')
            if not isinstance(result, dict):
                raise ValueError('config factory must return a dictionary value')
            return result
        else:
            config_dict = oauth.config


        rv = {}
        for k in params:
            conf_key = '{}_{}'.format(name, k).upper()
            v = config_dict.get(conf_key, None)
            if v is not None:
                rv[k] = v
        return rv

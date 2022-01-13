from rdmass.bot import client
from rdmass.config import config

if __name__ == "__main__":
    if config.sentry.dns:
        import sentry_sdk

        sentry_sdk.init(config.sentry.dns, traces_sample_rate=config.sentry.traces_sample_rate)

    client.run(config.bot.token)

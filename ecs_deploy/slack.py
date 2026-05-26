import re
import requests
from datetime import datetime, timezone

# Bound the HTTP calls to slack so a hung incoming-webhook endpoint cannot
# block the deployment indefinitely. Slack incoming webhooks return fast
# (<1s typical) for small payloads; 10s is generous. Without this, a
# misconfigured slack URL or DNS failure could leave the CLI hanging
# until the OS-level socket timeout (minutes).
REQUEST_TIMEOUT_SECONDS = 10


class SlackException(Exception):
    pass


class SlackNotification(object):
    def __init__(self, url, service_match):
        self.__url = url
        self.__service_match_re = re.compile(service_match or '')
        # `datetime.utcnow()` is deprecated in 3.12+ and slated for removal
        # in a future Python release. Use a timezone-aware UTC datetime
        # instead. `timezone.utc` (rather than `datetime.UTC`, which is
        # 3.11+) keeps compat with the project's declared 3.10 floor in
        # setup.py.
        self.__timestamp_start = datetime.now(timezone.utc)

    def get_payload(self, title, messages, color=None):
        fields = []
        for message in messages:
            field = {
                'title': message[0],
                'value': message[1],
                'short': True
            }
            fields.append(field)

        payload = {
            "username": "ECS Deploy",
            "attachments": [
                {
                    "pretext": title,
                    "color": color,
                    "fields": fields
                }
            ]
        }

        return payload

    def notify_start(self, cluster, tag, task_definition, comment, user, service=None, rule=None):
        if not self.__url or not self.__service_match_re.search(service or rule):
            return

        messages = [
            ('Cluster', cluster),
        ]

        if service:
            messages.append(('Service', service))

        if rule:
            messages.append(('Scheduled Task', rule))

        if tag:
            messages.append(('Tag', tag))

        if user:
            messages.append(('User', user))

        if comment:
            messages.append(('Comment', comment))

        for diff in task_definition.diff:
            if tag and diff.field == 'image' and diff.value.endswith(':' + tag):
                continue
            if diff.field == 'environment':
                messages.append(('Environment', '_sensitive (therefore hidden)_'))
                continue

            messages.append((diff.field, diff.value))

        payload = self.get_payload('Deployment has started', messages)

        response = requests.post(self.__url, json=payload, timeout=REQUEST_TIMEOUT_SECONDS)

        if response.status_code != 200:
            raise SlackException('Notifying deployment failed')

        return response

    def notify_success(self, cluster, revision, service=None, rule=None):
        if not self.__url or not self.__service_match_re.search(service or rule):
            return

        duration = datetime.now(timezone.utc) - self.__timestamp_start

        messages = [
            ('Cluster', cluster),
        ]

        if service:
            messages.append(('Service', service))
        if rule:
            messages.append(('Scheduled Task', rule))

        messages.append(('Revision', revision))
        messages.append(('Duration', str(duration)))

        payload = self.get_payload('Deployment finished successfully', messages, 'good')

        response = requests.post(self.__url, json=payload, timeout=REQUEST_TIMEOUT_SECONDS)

        if response.status_code != 200:
            raise SlackException('Notifying deployment failed')

    def notify_failure(self, cluster, error, service=None, rule=None):
        if not self.__url or not self.__service_match_re.search(service or rule):
            return

        duration = datetime.now(timezone.utc) - self.__timestamp_start

        messages = [
            ('Cluster', cluster),
        ]

        if service:
            messages.append(('Service', service))
        if rule:
            messages.append(('Scheduled Task', rule))

        messages.append(('Duration', str(duration)))
        messages.append(('Error', error))

        payload = self.get_payload('Deployment failed', messages, 'danger')

        response = requests.post(self.__url, json=payload, timeout=REQUEST_TIMEOUT_SECONDS)

        if response.status_code != 200:
            raise SlackException('Notifying deployment failed')

        return response

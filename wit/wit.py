import json
import logging
import os
import requests
import sys
import uuid

WIT_API_HOST = os.getenv('WIT_URL', 'https://api.wit.ai')
WIT_API_VERSION = os.getenv('WIT_API_VERSION', '20160516')
DEFAULT_MAX_STEPS = 5
INTERACTIVE_PROMPT = '> '
LEARN_MORE = 'Learn more at https://wit.ai/docs/quickstart'

class WitError(Exception):
    pass

def req(logger, access_token, meth, path, params, **kwargs):
    full_url = WIT_API_HOST + path
    logger.debug('%s %s %s', meth, full_url, params)
    headers = {
        'authorization': 'Bearer ' + access_token,
        'accept': 'application/vnd.wit.' + WIT_API_VERSION + '+json'
    }
    headers.update(kwargs.pop('headers', {}))
    rsp = requests.request(
        meth,
        full_url,
        headers=headers,
        params=params,
        **kwargs
    )
    if rsp.status_code > 200:
        raise WitError('Wit responded with status: ' + str(rsp.status_code) +
                       ' (' + rsp.reason + ')')
    json = rsp.json()
    if 'error' in json:
        raise WitError('Wit responded with an error: ' + json['error'])

    logger.debug('%s %s %s', meth, full_url, json)
    return json

def validate_actions(logger, actions):
    if not isinstance(actions, dict):
        logger.warn('The second parameter should be a dictionary.')
    for action in ['send']:
        if action not in actions:
            logger.warn('The \'' + action + '\' action is missing. ' +
                            LEARN_MORE)
    for action in actions.keys():
        if not hasattr(actions[action], '__call__'):
            logger.warn('The \'' + action +
                            '\' action should be a function.')
    return actions

class Wit:
    access_token = None
    actions = {}
    _sessions = {}

    def __init__(self, access_token, actions=None, logger=None):
        self.access_token = access_token
        self.logger = logger or logging.getLogger(__name__)
        if actions:
            self.actions = validate_actions(self.logger, actions)

    def message(self, msg, context=None, verbose=None):
        params = {}
        if verbose:
            params['verbose'] = True
        if msg:
            params['q'] = msg
        if context:
            params['context'] = json.dumps(context)
        resp = req(self.logger, self.access_token, 'GET', '/message', params)
        return resp

    def speech(self, audio_file, verbose=None, headers=None):
        
        params = {}
        headers = headers or {}
        if verbose:
            params['verbose'] = True
        resp = req(self.logger, self.access_token, 'POST', '/speech', params,
                   data=audio_file, headers=headers)
        return resp

    def converse(self, session_id, message, context=None, reset=None,
                 verbose=None):
        if context is None:
            context = {}
        params = {'session_id': session_id}
        if verbose:
            params['verbose'] = True
        if message:
            params['q'] = message
        if reset:
            params['reset'] = True
        resp = req(self.logger, self.access_token, 'POST', '/converse', params,
                   data=json.dumps(context))
        return resp

    def __run_actions(self, session_id, current_request, message, context, i,
                      verbose):
        if i <= 0:
            raise WitError('Max steps reached, stopping.')
        json = self.converse(session_id, message, context, verbose=verbose)
        if 'type' not in json:
            raise WitError('Couldn\'t find type in Wit response')
        if current_request != self._sessions[session_id]:
            return context

        self.logger.debug('Context: %s', context)
        self.logger.debug('Response type: %s', json['type'])
        if json['type'] == 'merge':
            json['type'] = 'action'
            json['action'] = 'merge'

        if json['type'] == 'error':
            raise WitError('Oops, I don\'t know what to do.')

        if json['type'] == 'stop':
            return context

        request = {
            'session_id': session_id,
            'context': dict(context),
            'text': message,
            'entities': json.get('entities'),
        }
        if json['type'] == 'msg':
            self.throw_if_action_missing('send')
            response = {
                'text': json.get('msg').encode('utf8'),
                'quickreplies': json.get('quickreplies'),
            }
            self.actions['send'](request, response)
        elif json['type'] == 'action':
            action = json['action']
            self.throw_if_action_missing(action)
            context = self.actions[action](request)
            if context is None:
                self.logger.warn('missing context - did you forget to return it?')
                context = {}
        else:
            raise WitError('unknown type: ' + json['type'])
        if current_request != self._sessions[session_id]:
            return context
        return self.__run_actions(session_id, current_request, None, context,
                                  i - 1, verbose)

    def run_actions(self, session_id, message, context=None,
                    max_steps=DEFAULT_MAX_STEPS, verbose=None):
        if not self.actions:
            self.throw_must_have_actions()
        if context is None:
            context = {}
        current_request = self._sessions[session_id] + 1 if session_id in self._sessions else 1
        self._sessions[session_id] = current_request

        context = self.__run_actions(session_id, current_request, message,
                                     context, max_steps, verbose)

        if current_request == self._sessions[session_id]:
            del self._sessions[session_id]

        return context

    def interactive(self, context=None, max_steps=DEFAULT_MAX_STEPS):
        
        if not self.actions:
            self.throw_must_have_actions()
        if max_steps <= 0:
            raise WitError('max iterations reached')
        if context is None:
            context = {}

        try:
            input_function = raw_input
        except NameError:
            input_function = input

        session_id = uuid.uuid1()
        while True:
            try:
                message = input_function(INTERACTIVE_PROMPT).rstrip()
            except (KeyboardInterrupt, EOFError):
                return
            context = self.run_actions(session_id, message, context, max_steps)

    def throw_if_action_missing(self, action_name):
        if action_name not in self.actions:
            raise WitError('unknown action: ' + action_name)

    def throw_must_have_actions(self):
        raise WitError('You must provide the `actions` parameter to be able to use runActions. ' + LEARN_MORE)

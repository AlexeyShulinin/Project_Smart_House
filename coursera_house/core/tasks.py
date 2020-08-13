from __future__ import absolute_import, unicode_literals

import requests as requests
from celery import task
from django.core.mail import send_mail
from django.core.mail import EmailMessage


from django.conf import settings

from .models import Setting

TOKEN = settings.SMART_HOME_ACCESS_TOKEN
url = settings.SMART_HOME_API_URL
headers = {'Authorization': f'Bearer {TOKEN}'}

"""
 Polling the controller and sending it what is happening inside the 
 core.tasks.smart_home_manager function. This function should be called 
 periodically at intervals of 5 seconds, for example using celery. 
 At the beginning of its work, the function requests data from the controller 
 using requests.get in the API, then analyzes the settings for the desired 
 temperature from the database, and in the current situation, and at the end, 
 if executed, makes requests.post in the API with a command for the controller, 
 if you need to send a letter, then sends it.
"""

def get_controller_settings():
	json_data = requests.get(url, headers=headers).json().get('data')
	data = dict()
	for control_panel in json_data:
		data[control_panel.get('name')] = control_panel.get('value')
	return data

@task()
def smart_home_manager():
	# get values from controller
	controller_data = get_controller_settings()

	print(controller_data)

	controller_update = {
		  'controllers': []
	}

	# If there is a water leak (leak_detector = true), close cold (cold_water = false)
	# and hot (hot_water = false) water and send a letter at the moment of detection.
	if controller_data.get('leak_detector'):
		if controller_data.get('cold_water'):
			controller_update['controllers'].append({'name': 'cold_water', 'value': False})
		if controller_data.get('hot_water'):
			controller_update['controllers'].append({'name': 'hot_water', 'value': False})
		if controller_data.get('washing_machine') == 'on' or controller_data.get('washing_machine') == 'broken':
			controller_update['controllers'].append({'name': 'washing_machine', 'value': 'off'})
		if controller_data.get('boiler'):
			controller_update['controllers'].append({'name': 'boiler', 'value': False})
		email = EmailMessage(
			'leak detector',
			'text',
			settings.EMAIL_HOST,
			[settings.EMAIL_RECEPIENT],
		)
		email.send(fail_silently=False)

	# If cold water (cold_water) is closed, immediately turn off
	# the boiler (boiler) and washing machine (washing_machine) and under
	# no circumstances turn them on until cold water is opened again.
	cold_water_exist = True
	if not controller_data.get('cold_water'):
		if controller_data.get('washing_machine') == 'on' or controller_data.get('washing_machine') == 'broken':
			controller_update['controllers'].append({'name': 'washing_machine', 'value': 'off'})
		if controller_data.get('boiler'):
			controller_update['controllers'].append({'name': 'boiler', 'value': False})
		cold_water_exist = False

	# If hot water has a temperature (boiler_temperature) less than
	# hot_water_target_temperature - 10%, you need to turn on the boiler (boiler)
	# and wait until it reaches the temperature hot_water_target_temperature + 10%,
	# after which in order to save energy, the boiler must be turned off

	hot_water_target_temperature = Setting.objects.get(controller_name='hot_water_target_temperature').value
	if controller_data.get('boiler_temperature') < 0.9*hot_water_target_temperature and cold_water_exist:
		if not controller_data.get('boiler'):
			controller_update['controllers'].append({'name': 'boiler', 'value': True})
	if controller_data.get('boiler_temperature') >= 1.1*hot_water_target_temperature:
		if controller_data.get('boiler'):
			controller_update['controllers'].append({'name': 'boiler', 'value': False})

	# If the curtains are partially open (curtains == “slightly_open”), then they are
	# on manual control - this means their state cannot be changed automatically under
	# any circumstances.
	curtains_slightly_open = False
	if controller_data.get('curtains') == 'slightly_open':
		curtains_slightly_open = True

	# If it is darker than 50 outside (outdoor_light), open the curtains (curtains),
	# but only if the lamp in the bedroom (bedroom_light) is not on. If outside (outdoor_light)
	# is lighter than 50, or the light in the bedroom (bedroom_light) is on, close the curtains.
	# Except when they are manually operated
	if controller_data.get('outdoor_light') < 50 and not controller_data.get('bedroom_light') and not curtains_slightly_open:
		if controller_data.get('curtains') == 'close' or controller_data.get('curtains') == 'slightly_open':
			controller_update['controllers'].append({'name': 'curtains', 'value': 'open'})
	if (controller_data.get('outdoor_light') > 50 or controller_data.get('bedroom_light')) and not curtains_slightly_open:
		if controller_data.get('curtains') == 'open' or controller_data.get('curtains') == 'slightly_open':
			controller_update['controllers'].append({'name': 'curtains', 'value': 'close'})

	# If smoke is detected (smoke_detector), immediately turn off the following appliances
	# [air_conditioner, bedroom_light, bathroom_light, boiler, washing_machine], and under
	# no circumstances turn them on until the smoke disappears.
	smoke_detector = False
	if controller_data.get('smoke_detector'):
		if controller_data.get('air_conditioner'):
			controller_update['controllers'].append({'name': 'air_conditioner', 'value': False})
		if controller_data.get('bedroom_light'):
			controller_update['controllers'].append({'name': 'bedroom_light', 'value': False})
		if controller_data.get('bathroom_light'):
			controller_update['controllers'].append({'name': 'bathroom_light', 'value': False})
		if controller_data.get('washing_machine') == 'on' or controller_data.get('washing_machine') == 'broken':
			controller_update['controllers'].append({'name': 'washing_machine', 'value': 'off'})
		if controller_data.get('boiler'):
			controller_update['controllers'].append({'name': 'boiler', 'value': False})
		smoke_detector = True


	# If the temperature in the bedroom (bedroom_temperature) has risen above
	# bedroom_target_temperature + 10%, turn on the air conditioner (air_conditioner),
	# and wait until the temperature drops below bedroom_target_temperature - 10%,
	# then turn off the air conditioner.

	bedroom_target_temperature = Setting.objects.get(controller_name='bedroom_target_temperature').value
	if controller_data.get('bedroom_temperature') > 1.1*bedroom_target_temperature and not smoke_detector:
		if not controller_data.get('air_conditioner'):
			controller_update['controllers'].append({'name': 'air_conditioner', 'value': True})
	if controller_data.get('bedroom_temperature') < 0.9*bedroom_target_temperature:
		if controller_data.get('air_conditioner'):
			controller_update['controllers'].append({'name': 'air_conditioner', 'value': False})

	if controller_update['controllers']:
		unique = []
		for item in controller_update['controllers']:
			if item not in unique:
				unique.append(item)
		controller_update['controllers'] = unique
		requests.post(url, headers=headers, json=controller_update)
	print(controller_update)




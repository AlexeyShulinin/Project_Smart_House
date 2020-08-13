import requests as requests
from django.urls import reverse_lazy
from django.views.generic import FormView

from .models import Setting
from .form import ControllerForm
from django.conf import settings

TOKEN = settings.SMART_HOME_ACCESS_TOKEN
url = settings.SMART_HOME_API_URL
headers = {'Authorization': f'Bearer {TOKEN}'}


class ControllerView(FormView):
	form_class = ControllerForm
	template_name = 'core/control.html'
	success_url = reverse_lazy('form')

	def get_context_data(self, **kwargs):
		context = super(ControllerView, self).get_context_data()
		# request for getting values from controllers
		data = get_controller_settings()
		print(data)
		# set data for visualization
		context['data'] = data
		return context

	def get_initial(self):
		initial = super(ControllerView, self).get_initial()
		# default values for form
		initial['bedroom_target_temperature'] = get_setting('bedroom_target_temperature')
		initial['hot_water_target_temperature'] = get_setting('hot_water_target_temperature')
		return initial

	def form_valid(self, form):
		get_or_update(
			'bedroom_target_temperature',
			'Bedroom target temperature',
			form.cleaned_data['bedroom_target_temperature']
		)
		get_or_update(
			'hot_water_target_temperature',
			'Hot water target temperature value',
			form.cleaned_data['hot_water_target_temperature']
		)
		return super(ControllerView, self).form_valid(form)


def get_or_update(controller_name, label, value):
	try:
		entry = Setting.objects.get(controller_name=controller_name)
	except Setting.DoesNotExist:
		Setting.objects.create(
			controller_name=controller_name,
			label=label,
			value=value
		)
	else:
		entry.value = value
		entry.save()

def get_controller_settings():
	json_data = requests.get(url, headers=headers).json().get('data')
	data = dict()
	for control_panel in json_data:
		data[control_panel.get('name')] = control_panel.get('value')
	return data

def get_setting(controller_name):
	entry = Setting.objects.get(controller_name=controller_name)
	return entry.value

app_name = "chef_alarab"
app_title = "Chef Alarab"
app_publisher = "sreejith"
app_description = "erpnext app"
app_email = "s@gmail.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "chef_alarab",
# 		"logo": "/assets/chef_alarab/logo.png",
# 		"title": "Chef Alarab",
# 		"route": "/chef_alarab",
# 		"has_permission": "chef_alarab.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/chef_alarab/css/chef_alarab.css"
# app_include_js = "/assets/chef_alarab/js/chef_alarab.js"

# include js, css files in header of web template
# web_include_css = "/assets/chef_alarab/css/chef_alarab.css"
# web_include_js = "/assets/chef_alarab/js/chef_alarab.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "chef_alarab/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
doctype_js = {"Sales Invoice": "public/js/sales_invoice.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "chef_alarab/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "chef_alarab.utils.jinja_methods",
# 	"filters": "chef_alarab.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "chef_alarab.install.before_install"
# after_install = "chef_alarab.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "chef_alarab.uninstall.before_uninstall"
# after_uninstall = "chef_alarab.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "chef_alarab.utils.before_app_install"
# after_app_install = "chef_alarab.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "chef_alarab.utils.before_app_uninstall"
# after_app_uninstall = "chef_alarab.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "chef_alarab.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }
doc_events = {
	"Sales Invoice": {
		"before_validate": "chef_alarab.events.sales_invoice.apply_vat_included_rate",
	}
}

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"chef_alarab.tasks.all"
# 	],
# 	"daily": [
# 		"chef_alarab.tasks.daily"
# 	],
# 	"hourly": [
# 		"chef_alarab.tasks.hourly"
# 	],
# 	"weekly": [
# 		"chef_alarab.tasks.weekly"
# 	],
# 	"monthly": [
# 		"chef_alarab.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "chef_alarab.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "chef_alarab.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "chef_alarab.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["chef_alarab.utils.before_request"]
# after_request = ["chef_alarab.utils.after_request"]

# Job Events
# ----------
# before_job = ["chef_alarab.utils.before_job"]
# after_job = ["chef_alarab.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"chef_alarab.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []


fixtures = [
	{
		"dt": "Custom Field",
		"filters": [["name", "in", ["Sales Invoice Item-custom_vat_included"]]],
	}
]

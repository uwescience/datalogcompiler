{% extends 'scan.cpp' %}

{% block initializer %}{{ super() }}, {{mapping_var_name}}{% endblock %}

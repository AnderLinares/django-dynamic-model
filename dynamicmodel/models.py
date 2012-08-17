from django.db import models
from django import forms
from django.contrib.contenttypes.models import ContentType
from django.core.validators import RegexValidator
from .fields import JSONField


class DynamicModel(models.Model):

    class Meta:
        abstract = True

    extra_fields = JSONField(editable=False, default="{}")

    def get_extra_field_value(self, key):
        if key in self.extra_fields:
            return self.extra_fields[key]
        else:
            return None

    def get_field_dict(self):
        d = self.extra_fields
        for field in self._meta.fields:
            if field.name == 'extra_fields':
                continue
            d[field.name] = getattr(self, field.name)
        return d

    def get_extra_fields(self):
        _schema = self.get_schema()
        for field in _schema.fields.all():
            yield field.name, field.field_type, field.required

    def get_extra_fields_names(self):
        return [name for name, field_type, required in self.get_extra_fields()]

    def get_schema(self):
        if not hasattr(self, '_schema'):
            self._schema = None

        if not self._schema:
            type_value = ''
            if self.get_schema_type_descriptor():
                type_value = getattr(self, self.get_schema_type_descriptor())
            self._schema, created = DynamicSchema.objects\
                .prefetch_related('fields').get_or_create(
                    type_value=type_value,
                    model=ContentType.objects.get_for_model(self))

        return self._schema

    def get_schema_type_descriptor(self):
        return ''

    def __getattr__(self, attr_name):
        if attr_name in self.extra_fields:
            return self.extra_fields[attr_name]
        else:
            return getattr(super(DynamicModel, self), attr_name)

    def __setattr__(self, attr_name, value):
        if hasattr(self, 'extra_fields') and \
            attr_name not in [el.name for el in self._meta.fields] and \
            attr_name not in ['_schema'] and \
            attr_name in self.get_extra_fields_names():

            self.extra_fields[attr_name] = value

        super(DynamicModel, self).__setattr__(attr_name, value)


class DynamicForm(forms.ModelForm):
    field_mapping = [
        ('IntegerField', {'field': forms.IntegerField}),
        ('CharField', {'field': forms.CharField}),
        ('TextField', {'field': forms.CharField, 'widget': forms.Textarea}),
        ('EmailField', {'field': forms.EmailField}),
    ]

    def __init__(self, *args, **kwargs):
        super(DynamicForm, self).__init__(*args, **kwargs)

        if not isinstance(self.instance, DynamicModel):
            raise ValueError("DynamicForm.Meta.model must be inherited from DynamicModel")

        if self.instance and hasattr(self.instance, 'get_extra_fields'):
            for name, field_type, req in self.instance.get_extra_fields():
                field_mapping_case = dict(self.field_mapping)[field_type]
                self.fields[name] = field_mapping_case['field'](required=req,
                    widget=field_mapping_case.get('widget'),
                    initial=self.instance.get_extra_field_value(name))

    def save(self, force_insert=False, force_update=False, commit=True):
        m = super(DynamicForm, self).save(commit=False)

        extra_fields = {}

        extra_fields_names = [name for name, field_type, req \
            in self.instance.get_extra_fields()]

        for cleaned_key in self.cleaned_data.keys():
            if cleaned_key in extra_fields_names:
                extra_fields[cleaned_key] = self.cleaned_data[cleaned_key]

        m.extra_fields = extra_fields

        if commit:
            m.save()
        return m


class DynamicSchema(models.Model):
    class Meta:
        unique_together = ('model', 'type_value')

    model = models.ForeignKey(ContentType)
    type_value = models.CharField(max_length=100, null=True, blank=True)

    def __unicode__(self):
        return "%s%s" % (self.model, " (%s)" % self.type_value if self.type_value else '')


class DynamicSchemaField(models.Model):
    FIELD_TYPES = [
        ('IntegerField', 'Integer number field'),
        ('CharField', 'One line of text'),
        ('TextField', 'Multiline text input'),
        ('EmailField', 'Email'),
    ]

    class Meta:
        unique_together = ('schema', 'name')

    schema = models.ForeignKey(DynamicSchema, related_name='fields')
    name = models.CharField(max_length=100, validators=[RegexValidator(r'^[\w]+$',
        message="Name should contain only alphanumeric characters and underscores.")])
    field_type = models.CharField(max_length=100, choices=FIELD_TYPES)
    required = models.BooleanField(default=True)

    def __unicode__(self):
        return "%s - %s" % (self.schema, self.name)
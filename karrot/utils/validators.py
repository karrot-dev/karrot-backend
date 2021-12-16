import re

from django.conf import settings
from rest_framework import serializers
from django.utils.translation import gettext as _

PASSWORD_BLACKLIST = [
    'P@ssw0rd', 'ka_dJKHJsy6', '1qaz!QAZ', '!QAZ2wsx', '1qaz@WSX', '!QAZ1qaz', 'fxzZ75$yer', 'Pa$$w0rd', 'Aug!272010',
    'L58jkdjP!m', 'ZV_!80lo', 'P@$$w0rd', 'ZAQ!2wsx', 'zaq1@WSX', 'g00dPa$$w0rD', 'Password1!', '!QAZxsw2', '1qazZAQ!',
    'Feder_1941', 'P@ssword1', 'P@55w0rd', '1qazXSW@', '$HEX[687474703a2f2f616473]', 'India@123', 'friendofEarning$1',
    '$HEX[687474703a2f2f777777]', 'Sym_cskill1', 't4_Us3r', 'Abc123456!', 'friendofYOUCANMAKE$200-', 'P@55word',
    'Password@123'
]


def prevent_reserved_names(value):
    if value.lower() in settings.RESERVED_NAMES:
        raise serializers.ValidationError(_('%(value)s is a reserved name') % {'value': value})


def contains_number(value):
    if re.search(r'\d', value) is None:
        raise serializers.ValidationError('password does not contain a number')


def contains_lowercase_letter(value):
    if re.search('[a-z]', value) is None:
        raise serializers.ValidationError('password does not contain a lowercase letter')


def contains_uppercase_letter(value):
    if re.search('[A-Z]', value) is None:
        raise serializers.ValidationError('password does not contain an uppercase letter')


def contains_special_character(value):
    if re.search('[@_!#$%^&*()<>?/}{~:|]', value) is None:
        raise serializers.ValidationError('password does not contain a special character')


def prevent_use_of_company_name(value):
    if re.search('karrot', value.lower()):
        raise serializers.ValidationError('password cannot contain company name')


def password_not_blacklisted(value):
    if value in PASSWORD_BLACKLIST:
        raise serializers.ValidationError('password is blacklisted')

from django import template

register = template.Library()

@register.filter(name='add_class')
def add_class(value, css_class):
    """
    Adds a given CSS class to the field widget.
    """
    if hasattr(value, 'as_widget'):
        return value.as_widget(attrs={'class': css_class})
    return value


@register.filter
def split(value, delimiter=","):
    return value.split(delimiter)

@register.filter
def is_allowed_doc(doc_type):
    return doc_type in ['Resume', 'Extra Dose of Covid', 'Other Documents']

@register.filter
def is_document_status_section_allowed_doc(doc_type_display_name):
    allowed_docs = [
        'Experience Document',
        'X-Ray Result',
        'MMR Lab/Vax Record',
        'Varicella Lab/Vax Record',
        'TDAP Vax Record',
        'Hepatitis B Lab/Vax Record',
        'Covid Vaccination Certificate',
        'Vulnerable Sector Check',
        'CPR or First Aid',
        'Mask Fit Certificate',
        'Basic Life Support',
        'Flu Shot',
        'Extra Dose of Covid',
        'Other Documents',
    ]
    return doc_type_display_name in allowed_docs

@register.filter
def document_group(doc_type_display_name):
    if doc_type_display_name == 'Experience Document':
        return 'Experience'
    elif doc_type_display_name in [
        'X-Ray Result',
        'MMR Lab/Vax Record',
        'Varicella Lab/Vax Record',
        'TDAP Vax Record',
        'Hepatitis B Lab/Vax Record',
    ]:
        return 'NACC Medical Report Form'
    elif doc_type_display_name in [
        'Covid Vaccination Certificate',
        'Vulnerable Sector Check',
        'CPR or First Aid',
        'Mask Fit Certificate',
        'Basic Life Support',
        'Flu Shot',
        'Extra Dose of Covid',
        'Other Documents',
    ]:
        return 'Required Documents'
    else:
        return ''
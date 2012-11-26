from django.http import HttpResponse
from django.utils import simplejson
from django.db.models import get_model
import stripe
from zebra.conf import options
from zebra.signals import *
from django.views.decorators.csrf import csrf_exempt

import logging
log = logging.getLogger("zebra.%s" % __name__)

stripe.api_key = options.STRIPE_SECRET

def _try_to_get_customer_from_customer_id(stripe_customer_id):
    if options.ZEBRA_CUSTOMER_MODEL:
        m = get_model(*options.ZEBRA_CUSTOMER_MODEL.split('.'))
        try:
            return m.objects.get(stripe_customer_id=stripe_customer_id)
        except:
            pass
    return None

@csrf_exempt
def webhooks(request):
    """
    Handles all known webhooks from stripe, and calls signals.
    Plug in as you need.
    """

    if request.method != "POST":
        return HttpResponse("Invalid Request.", status=400)

    json = simplejson.loads(request.POST["json"])

    if json["event"] == "recurring_payment_failed":
        zebra_webhook_recurring_payment_failed.send(sender=None, customer=_try_to_get_customer_from_customer_id(json["customer"]), full_json=json)

    elif json["event"] == "invoice_ready":
        zebra_webhook_invoice_ready.send(sender=None, customer=_try_to_get_customer_from_customer_id(json["customer"]), full_json=json)

    elif json["event"] == "recurring_payment_succeeded":
        zebra_webhook_recurring_payment_succeeded.send(sender=None, customer=_try_to_get_customer_from_customer_id(json["customer"]), full_json=json)

    elif json["event"] == "subscription_trial_ending":
        zebra_webhook_subscription_trial_ending.send(sender=None, customer=_try_to_get_customer_from_customer_id(json["customer"]), full_json=json)

    elif json["event"] == "subscription_final_payment_attempt_failed":
        zebra_webhook_subscription_final_payment_attempt_failed.send(sender=None, customer=_try_to_get_customer_from_customer_id(json["customer"]), full_json=json)

    elif json["event"] == "ping":
        zebra_webhook_subscription_ping_sent.send(sender=None)

    else:
        return HttpResponse(status=400)

    return HttpResponse(status=200)

@csrf_exempt
def webhooks_v2(request):
    """
    Handles all known webhooks from stripe, and calls signals.
    Plug in as you need.
    """
    if request.method != "POST":
        return HttpResponse("Invalid Request.", status=400)

    event_json = simplejson.loads(request.raw_post_data)
    event_key = event_json['type'].replace('.', '_')

    if event_key in WEBHOOK_MAP:
        WEBHOOK_MAP[event_key].send(sender=None, full_json=event_json)

    return HttpResponse(status=200)

@login_required  # Need a login page that knows how to handle redirect
def connect_redirect(request):
    # User should likely not need to wait for this to happen..
    opener = urllib2.build_opener()
    opener.addheaders = [('Authorization',
                          'Bearer %s' % settings.STRIPE_API_KEY)]
    post_data = {}
    post_data['code'] = request.GET['code']
    post_data['grant_type'] = 'authorization_code'
    result = opener.open('https://connect.stripe.com/oauth/token',
        urllib.urlencode(post_data))
    # Contains
    #   token_type
    #   scope
    #   refresh_token
    #   stripe_user_id
    #   stripe_publishable_key
    #   access_token
    # Need to store stripe_user_id with the user
    # and access_token to be able to pay them
    data = json.loads(result.read())

    stripe_user, created =\
    ConnectProfile.objects.get_or_create(user=request.user)

    stripe_user.stripe_id = data['stripe_user_id']
    stripe_user.access_token = data['access_token']
    stripe_user.save()

    #charge = stripe.Charge.create(
    #amount=400,
    #currency='usd',
    #api_key=data['access_token'],
    #)

    # Customers should get saved to _our_ stripe account and
    # not those Connect accounts, that way they can be re-used

    #stripe.api_key = settings.STRIPE_API_KEY
    #token = request.POST['stripeToken']
    #customer = stripe.Customer.create(
    #card = token,
    #)

    return TemplateResponse(request, 'stripe_connect/index.html', {})
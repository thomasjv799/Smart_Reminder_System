from twilio.rest import Client
import configparser

config = configparser.ConfigParser()
config.read("config.ini")


def twilio_messaging(message, from_, to):
    """
    Send a message to a group or to a user via Twilio API

    Parameters
    ----------
    message : dict
        Message to send
    from_ : str
        Sender's number. 
        Format: whatsapp:+14155238886
        Refer https://www.twilio.com/docs/whatsapp/quickstart/python
    to : str
        Receiver's number. 
        Format: whatsapp:+911234567890
        Refer https://www.twilio.com/docs/whatsapp/quickstart/python

    """
    twilio_account_sid = config.get("TwilioAPI", "account_sid")
    twilio_auth_token = config.get("TwilioAPI", "auth_token")

    # Define the credentials for accessing your Twilio account
    account_sid = twilio_account_sid
    auth_token = twilio_auth_token
    twilio_client = Client(account_sid, auth_token)

    twilio_client.messages.create(body=message, from_=from_, to=to)

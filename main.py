from datetime import date, datetime
from utils.gsheet import dataframe_from_gsheet
from utils.twilio_ import twilio_messaging
from utils.whin import WhinMsg


def smart_reminder(
    google_json_api,
    google_sheet_name,
    google_sheet_worksheet,
    from_,
    to_,
    twilio=True,
    whin=False,
):
    """
    Send a reminder message to a WhatsApp number if any of the vehicle's insurance or pollution fitness is due within 7 days

    Parameters
    ----------
    google_json_api : str
        Name of the JSON file containing the credentials for accessing your Google Sheet
    google_sheet_name : str
        Name of the Google Sheet
    google_sheet_worksheet : str
        Name of the worksheet in the Google Sheet
    from_ : str
        WhatsApp number from which the message will be sent
    to_ : str
        WhatsApp number to which the message will be sent
    twilio : bool, optional
        Whether to send the message via Twilio, by default True
    whin : bool, optional
        Whether to send the message via Whin, by default False
    """

    # Get the DataFrame from the Google Sheet
    df = dataframe_from_gsheet(
        google_json_api, google_sheet_name, google_sheet_worksheet
    )
    # Define the date format used in your Google Sheet
    date_format = "%d/%m/%Y"
    # Get today's date
    today = date.today()

    messages = []
    # Loop through the rows in the DataFrame and check for any reminders
    for i, row in df.iterrows():
        # Convert the date strings to datetime objects
        insurance_expiry = datetime.strptime(row["Insurance_Due"], date_format).date()
        pollution_fitness = datetime.strptime(row["Pollution"], date_format).date()
        # Calculate the number of days until each deadline
        insurance_days = (insurance_expiry - today).days
        pollution_days = (pollution_fitness - today).days
        # Send a reminder message if any deadline is within 7 days
        if insurance_days <= 7:
            message = f"{i+1}. Reminder: Vehicle {row.Name}, {row.Vehicle_No} insurance dated {row.Insurance_Due} expires in {insurance_days} days."
            messages.append(message)
        if pollution_days <= 7:
            message = f"{i+1}. Reminder: Vehicle {row.Name}, {row.Vehicle_No} insurance dated {row.Pollution} expires in {pollution_days} days."
            messages.append(message)

    # Join all the messages into a single string
    final_message = "\n\n".join([i for i in messages])
    if twilio == True:
        # Send the message via Twilio
        twilio_messaging(
            final_message, "whatsapp:{}".format(from_), "whatsapp:{}".format(to_)
        )
    if whin == True:
        # Send the message via Whin
        msg = {"text": final_message}
        WhinMsg(msg)


smart_reminder('ambient-mystery.json', 'Vehicle', 'Sheet1',"+14155238886", "+919400835799")

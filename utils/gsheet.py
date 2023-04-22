import gspread
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials


def dataframe_from_gsheet(json_file_name, file_name, worksheet_name):
    """
    Load a Google Sheet into a Pandas DataFrame

    Parameters
    ----------
    json_file_name : str
        Name of the JSON file containing the credentials for accessing your Google Sheet
    file_name : str
        Name of the Google Sheet
    worksheet_name : str
        Name of the worksheet in the Google Sheet
        
    Returns
    -------
    df : Pandas DataFrame
        DataFrame containing the data from the Google Sheet
    """
    # Define the credentials for accessing your Google Sheet
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_name(json_file_name, scope)
    client = gspread.authorize(creds)
    # Open the Google Sheet
    gsheet = client.open(file_name)
    # Open the worksheet
    sheet = gsheet.worksheet(worksheet_name)
    # Load the data into a Pandas DataFrame
    df = pd.DataFrame(sheet.get_all_records())

    return df

import requests
import configparser

config = configparser.ConfigParser()
config.read("config.ini")


def sendWSP(message, apikey, gid=0):
    """
    Send a message to a group or to a user via Whin API
    Watch : https://www.youtube.com/watch?v=0EzTdm22VHI

    Parameters
    ----------
    message : dict
        Message to send
    apikey : str
        API key for Whin API
    gid : int

    Returns
    -------
    requests.Response
        Response from Whin API
    """
    url = "https://whin2.p.rapidapi.com/send"
    headers = {
        "content-type": "application/json",
        "X-RapidAPI-Key": apikey,
        "X-RapidAPI-Host": "whin2.p.rapidapi.com",
    }
    try:
        if gid == 0:
            return requests.request("POST", url, json=message, headers=headers)
        else:
            url = "https://whin2.p.rapidapi.com/send2group"
            querystring = {"gid": gid}
            return requests.request(
                "POST", url, json=message, headers=headers, params=querystring
            )
    except requests.ConnectionError:
        return "Error: Connection Error"


def WhinMsg(message):
    """
    Send a message to a group or to a user via Whin API

    Parameters
    ----------
    message : dict
        Message to send
    
    """

    WhinAPI = config.get("WhinAPI", "apikey")
    WhinGrpID = config.get("WhinAPI", "groupid")
    sendWSP(message, WhinAPI, WhinGrpID)

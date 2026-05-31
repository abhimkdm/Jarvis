import win32com.client as win32

class OutlookAgent:
    def __init__(self):
        pass

    def run(self, data_payload):
        """
        Generic operational automation runner for Outlook.
        Expects data_payload to be a dict: {"recipient": str, "body": str}
        """
        try:
            recipient = data_payload.get("recipient", "Unknown")
            body_text = data_payload.get("body", "")
            
            print(f"[Agent Fleet: Initializing Outlook COM link for target: {recipient}...]")
            
            # Hook into local Windows Outlook engine
            outlook = win32.Dispatch('outlook.application')
            mail = outlook.CreateItem(0)
            
            # DYNAMICALLY ASSIGN VALUES FROM THE PAYLOAD DICTIONARY
            mail.To = recipient 
            mail.Subject = f"Automated Desktop Note regarding {recipient}"
            mail.Body = body_text
            
            print(f"[Agent Fleet: Launching draft interface window...]")
            mail.Display()
            
            return f"I have successfully generated a generic Outlook email draft for '{recipient}', sir."
        except Exception as e:
            return f"Outlook Agent operational execution error: {e}"
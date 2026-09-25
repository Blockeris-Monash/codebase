import asyncio
import sys
sys.path.append('.')
from backend.si_request import generate_pdf

async def main():
    print("Simulating AI extraction because APIs are currently rate-limited...")
    mock_fields = {
        "shipper": {"present": True, "raw": "APRIL FINE PAPER TRADING\nON BEHALF OF VITAL SOLUTIONS PTE LTD\n77 ROBINSON ROAD, #21-01\nSINGAPORE 068896"},
        "consignee": {"present": True, "raw": "ROXCEL TRADING GMBH\nOPERNRING 3-5\n1010 VIENNA, AUSTRIA"},
        "notify_party": {"present": True, "raw": "ROXCEL TRADING GMBH\nOPERNRING 3-5\n1010 VIENNA, AUSTRIA"},
        "port_of_loading": {"present": True, "raw": "RUGAO/NANTONG/SHANGHAI, CHINA"},
        "port_of_discharge": {"present": True, "raw": "PYEONGTAEK, SOUTH KOREA"},
        "container_count": {"present": True, "raw": "5X40'HC"},
        "gross_weight_kg": {"present": True, "raw": "120,000 KG"}
    }
    
    email_id = "email_022"
    pdf_path = generate_pdf(mock_fields, email_id)
    print("SUCCESS!")
    print("Generated Draft BL PDF at:", pdf_path)

if __name__ == '__main__':
    asyncio.run(main())

import asyncio
import sys
sys.path.append('.')
from backend.classify import EmailInput
from backend.si_request import process_si_request

async def main():
    email = EmailInput(
        email_id="email_022",
        from_email="elisa_tukiman@april.com.my",
        subject="CUST SI MEA 5RCY-52735 __ PO_25_5465",
        body="""Hi Hari

Please find Shipping instruction for 5RCY-52735.

POL: RUGAO/NANTONG/SHANGHAI, CHINA
POD: PYEONGTAEK, SOUTH KOREA

Shipper:
APRIL FINE PAPER TRADING
ON BEHALF OF VITAL SOLUTIONS PTE LTD
77 ROBINSON ROAD, #21-01
SINGAPORE 068896

Consignee:
ROXCEL TRADING GMBH
OPERNRING 3-5
1010 VIENNA, AUSTRIA

Notify Party:
ROXCEL TRADING GMBH
OPERNRING 3-5
1010 VIENNA, AUSTRIA

Description of Goods:
5X40'HC
UNCOATED WOODFREE PAPER IN REAM

Container count: 5
Gross weight: 120,000 KG
""",
        attachments=[]
    )
    
    reply, pdf_path, fields = await asyncio.to_thread(process_si_request, email)
    print("REPLY:")
    print(reply)
    print("PDF PATH:", pdf_path)
    
if __name__ == '__main__':
    asyncio.run(main())

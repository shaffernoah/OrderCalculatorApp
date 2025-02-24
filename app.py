import streamlit as st
import pandas as pd
import altair as alt
from supabase import create_client, Client
import os
from datetime import datetime, timedelta
import tempfile
import re
import subprocess
from PIL import Image
from pdf2image import convert_from_path
import pytesseract
from dateutil import parser

# Initialize Supabase client
supabase: Client = create_client(
    st.secrets["SUPABASE_URL"],
    st.secrets["SUPABASE_KEY"]
)

# Verify database connection
def init_db():
    try:
        # Test connection by trying to select from tables
        supabase.table('inventory').select("*").limit(1).execute()
        supabase.table('orders').select("*").limit(1).execute()
        supabase.table('production').select("*").limit(1).execute()
        st.sidebar.success('Connected to Supabase')
    except Exception as e:
        st.sidebar.error('Error connecting to database. Please ensure tables are created.')
        st.sidebar.error(str(e))

# Initialize database connection
init_db()

# Product details and yields
products = {
    'WF Kosher Boneless Beef Ribeye Steak': {
        'avg_case_weight': 10,
        'raw_material': 'RIBEYE',
        'yield': 0.75,
        'production_cost': 1.58
    },
    'WF Kosher Boneless Beef Brisket Flat Cut': {
        'avg_case_weight': 22,
        'raw_material': 'BRISKET',
        'yield': 0.4551971326,  # Brisket Flat yield
        'production_cost': 1.38,
        'related_yields': {
            'Stew': 0.1935483871,  # Will generate this much stew from the same input
            'Grind': 0.1775822744  # Will generate this much grind from the same input
        }
    },
    'WF Kosher Boneless Beef Chuck Roast': {
        'avg_case_weight': 11,
        'raw_material': '2PC CHUCK',
        'yield': 0.2734375,
        'production_cost': 1.19,
        'related_yields': {
            'Short Rib': 0.1789,
            'Grind': 0.489375
        }
    },
    'WF Kosher Ground Beef Blend of Chuck & Brisket (80/20)': {
        'avg_case_weight': 12,
        'raw_material': '2PC CHUCK',
        'yield': 0.489375,  # Using the Trim yield
        'production_cost': 1.11
    },
    'WF Kosher Beef Outside Skirt Steak': {
        'avg_case_weight': 19,
        'raw_material': 'OUTSIDE SKIRT',
        'yield': 0.85,
        'production_cost': 1.52
    },
    'WF Kosher Boneless Beef Short Ribs': {
        'avg_case_weight': 13,
        'raw_material': '2PC CHUCK',
        'yield': 0.1789,
        'production_cost': 1.51,
        'related_yields': {
            'Chuck Roast': 0.2734375,
            'Grind': 0.489375
        }
    },
    'WF Kosher Beef Stew': {
        'avg_case_weight': 8,
        'raw_material': '2PC CHUCK',
        'yield': 0.489375,  # Trim portion for ground beef
        'production_cost': 1.83
    }
}

def calculate_ribeye(quantity):
    info = products['WF Kosher Boneless Beef Ribeye Steak']
    raw_material = quantity / info['yield']
    cost = raw_material * info['production_cost']
    return {
        'product': 'RIBEYE',
        'order_quantity': quantity,
        'raw_material': raw_material,
        'cost': cost
    }

def calculate_brisket(quantity):
    info = products['WF Kosher Boneless Beef Brisket Flat Cut']
    raw_material = quantity / info['yield']
    cost = raw_material * info['production_cost']
    additional_outputs = []
    if 'related_yields' in info:
        for output, yield_rate in info['related_yields'].items():
            output_quantity = raw_material * yield_rate
            additional_outputs.append({
                'product': output,
                'quantity': output_quantity
            })
    return {
        'product': 'BRISKET',
        'order_quantity': quantity,
        'raw_material': raw_material,
        'cost': cost,
        'additional_outputs': additional_outputs
    }

def calculate_chuck_roast(quantity):
    info = products['WF Kosher Boneless Beef Chuck Roast']
    raw_material = quantity / info['yield']
    cost = raw_material * info['production_cost']
    additional_outputs = []
    if 'related_yields' in info:
        for output, yield_rate in info['related_yields'].items():
            output_quantity = raw_material * yield_rate
            additional_outputs.append({
                'product': output,
                'quantity': output_quantity
            })
    return {
        'product': 'CHUCK ROAST',
        'order_quantity': quantity,
        'raw_material': raw_material,
        'cost': cost,
        'additional_outputs': additional_outputs
    }

def calculate_outside_skirt(quantity):
    info = products['WF Kosher Beef Outside Skirt Steak']
    raw_material = quantity / info['yield']
    cost = raw_material * info['production_cost']
    return {
        'product': 'OUTSIDE SKIRT',
        'order_quantity': quantity,
        'raw_material': raw_material,
        'cost': cost
    }

def calculate_stew(quantity):
    info = products['WF Kosher Beef Stew']
    raw_material = quantity / info['yield']
    cost = raw_material * info['production_cost']
    return {
        'product': 'STEW',
        'order_quantity': quantity,
        'raw_material': raw_material,
        'cost': cost
    }

def calculate_short_rib(quantity):
    info = products['WF Kosher Boneless Beef Short Ribs']
    raw_material = quantity / info['yield']
    cost = raw_material * info['production_cost']
    return {
        'product': 'BNLS SHORT RIB',
        'order_quantity': quantity,
        'raw_material': raw_material,
        'cost': cost
    }

def order_planning():
    st.title('Order Planning')
    st.markdown('Create and manage purchase orders')
    
    # Custom CSS for styling
    st.markdown("""
        <style>
        .main {
            font-size: 18px;
        }
        .valid-input {
            border-color: #28a745 !important;
        }
        .invalid-input {
            border-color: #dc3545 !important;
        }
        @media (max-width: 768px) {
            .stColumns {
                gap: 0.5rem;
            }
        }
        </style>
    """, unsafe_allow_html=True)
    
    # Initialize session state
    if 'item_count' not in st.session_state:
        st.session_state.item_count = 1
    if 'notes' not in st.session_state:
        st.session_state.notes = ""
    
    # Order templates
    templates = {
        'Default': [],
        'Common Order A': [
            {'product': 'WF Kosher Boneless Beef Ribeye Steak', 'quantity': 100},
            {'product': 'WF Kosher Boneless Beef Brisket Flat Cut', 'quantity': 50},
        ],
        'Common Order B': [
            {'product': 'WF Kosher Boneless Beef Chuck Roast', 'quantity': 75},
            {'product': 'WF Kosher Beef Outside Skirt Steak', 'quantity': 25},
        ]
    }
    
    # Header section
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        po_number = st.text_input('PO Number', placeholder='Enter PO number')
    with col2:
        po_date = st.date_input('PO Date', value=datetime.now().date())
    with col3:
        delivery_date = st.date_input('Delivery Date', value=(datetime.now() + timedelta(days=7)).date())

    # Template selection
    template = st.selectbox('Load Template', ['Default'] + list(templates.keys())[1:])
    if template != 'Default' and template in templates:
        st.session_state.item_count = len(templates[template])
    
    # Product list for dropdown - using exact names from products dictionary
    product_list = [
        'WF Kosher Boneless Beef Ribeye Steak',
        'WF Kosher Boneless Beef Brisket Flat Cut',
        'WF Kosher Boneless Beef Chuck Roast',
        'WF Kosher Beef Outside Skirt Steak',
        'WF Kosher Beef Stew',
        'WF Kosher Boneless Beef Short Ribs'
    ]
    
    # Line items
    st.markdown('### Line Items')
    
    line_items = []
    total_cost = 0
    
    for i in range(st.session_state.item_count):
        col1, col2 = st.columns([2, 1])
        
        with col1:
            if template != 'Default' and i < len(templates[template]):
                default_product = templates[template][i]['product']
                default_quantity = templates[template][i]['quantity']
            else:
                default_product = product_list[0]
                default_quantity = 0
            
            product = st.selectbox(
                f'Product {i+1}',
                product_list,
                key=f'product_{i}',
                index=product_list.index(default_product) if default_product in product_list else 0
            )
        
        with col2:
            quantity = st.number_input(
                f'Quantity (lbs) {i+1}',
                min_value=0.0,
                value=float(default_quantity),
                step=0.1,
                key=f'quantity_{i}',
                help='Enter quantity in pounds'
            )
        
        if product and quantity > 0:
            line_items.append({
                'product': product,
                'quantity': quantity
            })
    
    # Add/Remove item buttons
    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button('+ Add Item'):
            st.session_state.item_count += 1
            st.rerun()
    
    # Notes section
    st.markdown('### Notes')
    notes = st.text_area('Order Notes', value=st.session_state.notes, height=100)
    st.session_state.notes = notes
    
    # Calculate order
    if st.button('Calculate Order', type='primary'):
        if not po_number:
            st.error('Please enter a PO number')
            return
        
        if not line_items:
            st.error('Please add at least one line item')
            return
        
        results = []
        total_cost = 0
        
        # Calculate each line item
        for item in line_items:
            if item['product'] == 'WF Kosher Boneless Beef Ribeye Steak' and item['quantity'] > 0:
                result = calculate_ribeye(item['quantity'])
                results.append(result)
                total_cost += result['cost']
            elif item['product'] == 'WF Kosher Boneless Beef Brisket Flat Cut' and item['quantity'] > 0:
                result = calculate_brisket(item['quantity'])
                results.append(result)
                total_cost += result['cost']
            elif item['product'] == 'WF Kosher Boneless Beef Chuck Roast' and item['quantity'] > 0:
                result = calculate_chuck_roast(item['quantity'])
                results.append(result)
                total_cost += result['cost']
            elif item['product'] == 'WF Kosher Beef Outside Skirt Steak' and item['quantity'] > 0:
                result = calculate_outside_skirt(item['quantity'])
                results.append(result)
                total_cost += result['cost']
            elif item['product'] == 'WF Kosher Beef Stew' and item['quantity'] > 0:
                result = calculate_stew(item['quantity'])
                results.append(result)
                total_cost += result['cost']
            elif item['product'] == 'WF Kosher Boneless Beef Short Ribs' and item['quantity'] > 0:
                result = calculate_short_rib(item['quantity'])
                results.append(result)
                total_cost += result['cost']
        
        # Display results
        st.markdown("---")
        st.markdown("### Order Summary")
        
        # Create summary table
        summary_data = []
        for result in results:
            summary_data.append({
                'Product': result['product'],
                'Order Quantity (lbs)': f"{result['order_quantity']:.1f}",
                'Raw Material (lbs)': f"{result['raw_material']:.1f}",
                'Cost': f"${result['cost']:.2f}"
            })
            
            # Add additional outputs if present
            if 'additional_outputs' in result:
                for output in result['additional_outputs']:
                    summary_data.append({
                        'Product': f"→ {output['product']}",
                        'Order Quantity (lbs)': f"{output['quantity']:.1f}",
                        'Raw Material (lbs)': '-',
                        'Cost': '-'
                    })
        
        # Display summary table
        st.table(pd.DataFrame(summary_data))
        st.markdown(f"**Total Estimated Cost:** ${total_cost:.2f}")
        
        # Create CSV for download
        csv = pd.DataFrame(summary_data).to_csv(index=False)
        st.download_button(
            'Download Summary',
            csv,
            'order_summary.csv',
            'text/csv'
        )
        
        # Save order to database
        try:
            response = supabase.table('orders').insert({
                'po_number': po_number,
                'po_date': po_date.isoformat(),
                'delivery_date': delivery_date.isoformat(),
                'line_items': line_items,
                'total_cost': total_cost,
                'notes': notes
            }).execute()
            
            if hasattr(response, 'data'):
                st.success('Order saved successfully!')
                st.markdown(f"View this order on the **Order Board** tab")
            else:
                st.error('Error saving order')
        except Exception as e:
            st.error(f'Error saving order: {str(e)}')

def inventory_tracking():
    st.title('Inventory Tracking')
    st.markdown('Record raw material orders and production records below.')
    
    tab1, tab2, tab3, tab4 = st.tabs(["Raw Material Purchase", "Upload Invoice", "Production Record", "Document Management"])
    
    with tab1:
        with st.form('inventory_purchase_form'):
            material = st.selectbox('Raw Material', ['RIBEYE', 'BRISKET', '2PC CHUCK', 'OUTSIDE SKIRT'])
            quantity = st.number_input('Quantity (lbs)', min_value=0.0, step=0.1, value=0.0)
            cost = st.number_input('Total Cost ($)', min_value=0.0, step=0.1, value=0.0)
            invoice_number = st.text_input('Invoice Number')
            purchase_date = st.date_input('Purchase Date', value=datetime.now())
            submitted = st.form_submit_button('Add Purchase Record')
            
            if submitted:
                if quantity > 0 and cost > 0:
                    # Calculate price per pound
                    price_per_lb = cost / quantity if quantity > 0 else 0
                    
                    data = {
                        'material': material,
                        'quantity': quantity,
                        'cost': cost,
                        'purchase_date': purchase_date.isoformat(),
                        'transaction_type': 'purchase',
                        'price_per_lb': price_per_lb,
                        'invoice_number': invoice_number
                    }
                    
                    try:
                        response = supabase.table('inventory_purchases').insert(data).execute()
                        if hasattr(response, 'data'):
                            st.success('Purchase record added successfully')
                        else:
                            st.error('Error adding purchase record')
                    except Exception as e:
                        st.error(f'Error adding purchase record: {str(e)}')
                else:
                    st.error('Quantity and cost must be greater than 0')
    
    with tab2:
        st.subheader("Upload Invoice PDF")
        uploaded_file = st.file_uploader("Choose a PDF file", type="pdf", key="invoice_upload")
        
        if uploaded_file is not None:
            try:
                # Create a temporary file
                temp_dir = tempfile.mkdtemp()
                temp_path = os.path.join(temp_dir, "temp.pdf")
                
                with open(temp_path, "wb") as f:
                    f.write(uploaded_file.getvalue())
                
                # Store PDF in Supabase storage
                file_path = f"invoices/{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uploaded_file.name}"
                with open(temp_path, "rb") as f:
                    supabase.storage.from_("documents").upload(file_path, f)
                
                # Continue with existing PDF processing code
                # Use absolute path to Poppler
                poppler_path = "/opt/homebrew/Cellar/poppler/25.02.0/bin"
                st.success(f"Using Poppler at: {poppler_path}")
                
                # Convert PDF to images with explicit path
                try:
                    images = convert_from_path(
                        temp_path,
                        poppler_path=poppler_path,
                        dpi=300,  # Increase DPI for better quality
                        fmt='jpeg'  # Use JPEG format for better OCR
                    )
                    st.success(f"Successfully converted PDF to {len(images)} images")
                except Exception as e:
                    st.error(f"Error converting PDF: {str(e)}")
                    st.error("Detailed error information:")
                    st.error(f"Poppler path exists: {os.path.exists(poppler_path)}")
                    st.error(f"Poppler binaries:")
                    st.code("\n".join(os.listdir(poppler_path)))
                    st.error(f"PDF path exists: {os.path.exists(temp_path)}")
                    st.error(f"PDF size: {os.path.getsize(temp_path)} bytes")
                    raise e
                
                # Extract text using OCR
                try:
                    # Verify Tesseract installation
                    tesseract_version = subprocess.check_output([pytesseract.pytesseract.tesseract_cmd, '--version']).decode()
                    st.success(f"Using Tesseract version: {tesseract_version.split()[1]}")
                    
                    extracted_text = ""
                    for idx, image in enumerate(images):
                        st.info(f"Processing page {idx + 1}...")
                        page_text = pytesseract.image_to_string(image)
                        extracted_text += f"\n--- Page {idx + 1} ---\n{page_text}"
                    st.success("OCR completed successfully")
                except Exception as e:
                    st.error(f"Error performing OCR: {str(e)}")
                    st.error("Detailed error information:")
                    st.error(f"Tesseract path exists: {os.path.exists('/opt/homebrew/bin/tesseract')}")
                    st.error(f"Tesseract path is executable: {os.access('/opt/homebrew/bin/tesseract', os.X_OK)}")
                    raise e
                
                # Define patterns for different invoice formats
                patterns = {
                    'date': r'(?i)Invoice Date:\s*(\d{2}/\d{2}/\d{4})',
                    'invoice_number': r'(?i)Invoice\s*\n(\d+)',
                    'line_items': r'(?im)^\d+\s+\d+\s+(.*?)\s+([0-9,]+\.\d+)\s+LB\s+([0-9.]+)\s+([0-9,]+\.\d+)$'
                }

                # Product name mapping for standardization
                product_mapping = {
                    'chuck 2pc bnls': '2PC CHUCK',
                    'chuck 2pc': '2PC CHUCK',
                    'outside skirt': 'OUTSIDE SKIRT',
                    'brisket': 'BRISKET',
                    'ribeye': 'RIBEYE'
                }

                # Extract information
                extracted_info = {
                    'date': None,
                    'invoice_number': None,
                    'line_items': []
                }

                # Extract date
                date_match = re.search(patterns['date'], extracted_text)
                if date_match:
                    extracted_info['date'] = date_match.group(1)

                # Extract invoice number
                invoice_match = re.search(patterns['invoice_number'], extracted_text)
                if invoice_match:
                    extracted_info['invoice_number'] = invoice_match.group(1)

                # Extract line items
                line_items = re.finditer(patterns['line_items'], extracted_text)
                for match in line_items:
                    product_desc, quantity, price_per_lb, total = match.groups()
                    
                    # Clean up the extracted values
                    product_desc = product_desc.lower().strip()
                    quantity = float(quantity.replace(',', ''))
                    price_per_lb = float(price_per_lb)
                    total = float(total.replace(',', ''))
                    
                    # Find matching standardized product name
                    standardized_product = None
                    for key, value in product_mapping.items():
                        if key in product_desc:
                            standardized_product = value
                            break
                    
                    if standardized_product:
                        extracted_info['line_items'].append({
                            'product': standardized_product,
                            'quantity': quantity,
                            'price_per_lb': price_per_lb,
                            'total': total
                        })

                # Display raw extracted text in expander
                with st.expander("View Raw Extracted Text"):
                    st.text(extracted_text)

                # Display extracted information for verification
                st.subheader("Invoice Details")
                col1, col2 = st.columns(2)
                with col1:
                    if extracted_info['date']:
                        try:
                            parsed_date = parser.parse(extracted_info['date'])
                            invoice_date = st.date_input("Invoice Date", value=parsed_date)
                        except:
                            invoice_date = st.date_input("Invoice Date")
                    else:
                        invoice_date = st.date_input("Invoice Date")

                with col2:
                    invoice_number = st.text_input(
                        "Invoice Number",
                        value=extracted_info.get('invoice_number', ''),
                        placeholder="Enter invoice number"
                    )

                st.subheader("Line Items")
                st.info("Please verify and correct the extracted information if needed")

                if not extracted_info['line_items']:
                    st.warning("No line items were found in the invoice. Please check the raw text and verify the format.")
                else:
                    for idx, item in enumerate(extracted_info['line_items']):
                        st.markdown(f"### Line Item {idx + 1}")
                        col1, col2, col3 = st.columns(3)
                        
                        with col1:
                            item['product'] = st.selectbox(
                                "Raw Material",
                                ['RIBEYE', 'BRISKET', '2PC CHUCK', 'OUTSIDE SKIRT'],
                                index=['RIBEYE', 'BRISKET', '2PC CHUCK', 'OUTSIDE SKIRT'].index(item['product']),
                                key=f"product_{idx}"
                            )
                            
                            item['quantity'] = st.number_input(
                                "Quantity (lbs)",
                                value=item['quantity'],
                                step=0.1,
                                key=f"quantity_{idx}"
                            )
                        
                        with col2:
                            item['price_per_lb'] = st.number_input(
                                "Price per lb ($)",
                                value=item['price_per_lb'],
                                step=0.0001,
                                format="%.4f",
                                key=f"price_{idx}"
                            )
                        
                        with col3:
                            item['total'] = st.number_input(
                                "Total Cost ($)",
                                value=item['total'],
                                step=0.01,
                                key=f"total_{idx}"
                            )
                            
                            # Add a calculated field to show verification
                            calculated_total = item['quantity'] * item['price_per_lb']
                            if abs(calculated_total - item['total']) > 0.01:
                                st.warning(f"Calculated total (${calculated_total:.2f}) differs from invoice total (${item['total']:.2f})")

                if st.button("Confirm and Save All Items"):
                    for item in extracted_info['line_items']:
                        data = {
                            'material': item['product'],
                            'quantity': item['quantity'],
                            'price_per_lb': item['price_per_lb'],
                            'cost': item['total'],
                            'purchase_date': invoice_date.isoformat(),
                            'invoice_number': invoice_number,
                            'transaction_type': 'purchase'
                        }
                        
                        response = supabase.table('inventory_purchases').insert(data).execute()
                        
                        if hasattr(response, 'data'):
                            st.success(f'Successfully saved {item["product"]} purchase record')
                        else:
                            st.error(f'Error saving {item["product"]} purchase record')

                # After successful processing, store document metadata in the database
                doc_data = {
                    'file_name': uploaded_file.name,
                    'file_path': file_path,
                    'doc_type': 'invoice',
                    'upload_date': datetime.now().isoformat()
                }
                supabase.table('documents').insert(doc_data).execute()
                
                # Cleanup temporary files
                os.remove(temp_path)
                os.rmdir(temp_dir)
                
            except Exception as e:
                st.error(f"Error processing PDF: {str(e)}")
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                if os.path.exists(temp_dir):
                    os.rmdir(temp_dir)
                
                # Show detailed system information
                st.error("System Information:")
                try:
                    brew_prefix = subprocess.check_output(['/opt/homebrew/bin/brew', '--prefix']).decode().strip()
                    st.code(f"""
                    Homebrew prefix: {brew_prefix}
                    Poppler installation:
                    {subprocess.check_output(['ls', '-l', f'{brew_prefix}/bin/pdftoppm']).decode()}
                    
                    PATH environment:
                    {os.environ.get('PATH', 'PATH not set')}
                    """)
                except Exception as sys_e:
                    st.error(f"Error getting system information: {str(sys_e)}")
    
    with tab4:
        st.subheader("Document Management")
        
        # Document filters
        col1, col2 = st.columns(2)
        with col1:
            doc_type_filter = st.selectbox(
                "Document Type",
                ["All", "Invoice", "Production Record", "Other"],
                key="doc_type_filter"
            )
        with col2:
            date_filter = st.date_input(
                "Date Filter",
                value=(datetime.now() - timedelta(days=30), datetime.now()),
                key="date_filter"
            )
        
        # Fetch documents from database
        query = supabase.table('documents').select('*')
        if doc_type_filter != "All":
            query = query.eq('doc_type', doc_type_filter.lower())
        if len(date_filter) == 2:
            query = query.gte('upload_date', date_filter[0].isoformat()).lte('upload_date', date_filter[1].isoformat())
        
        documents = query.execute()
        
        if not documents.data:
            st.info("No documents found matching the criteria")
        else:
            for doc in documents.data:
                with st.expander(f"{doc['file_name']} - {doc['upload_date'][:10]}"):
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.text(f"Document Type: {doc['doc_type'].title()}")
                        if doc['doc_type'] == 'invoice':
                            st.text(f"Invoice Number: {doc['invoice_number']}")
                            st.text(f"Invoice Date: {doc['invoice_date'][:10] if doc['invoice_date'] else 'N/A'}")
                        
                        # Show extracted text directly without nested expander
                        if doc.get('extracted_text'):
                            st.markdown("**Extracted Text:**")
                            st.text_area("", value=doc['extracted_text'], height=200, key=f"text_{doc['id']}", disabled=True)
                    
                    with col2:
                        # Generate temporary URL for download
                        try:
                            download_url = supabase.storage.from_("documents").create_signed_url(
                                doc['file_path'],
                                60  # URL valid for 60 seconds
                            )
                            st.markdown(f"[Download Document]({download_url['signedURL']})")
                        except Exception as e:
                            st.error("Error generating download link")
    
    with tab3:
        with st.form('production_record_form'):
            product = st.selectbox('Product', list(products.keys()))
            input_material = st.selectbox('Input Material', ['RIBEYE', 'BRISKET', '2PC CHUCK', 'OUTSIDE SKIRT'])
            input_quantity = st.number_input('Input Quantity (lbs)', min_value=0.0, step=0.1, value=0.0)
            output_quantity = st.number_input('Output Quantity (lbs)', min_value=0.0, step=0.1, value=0.0)
            
            submitted = st.form_submit_button('Add Production Record')
            
            if submitted:
                if input_quantity > 0 and output_quantity > 0:
                    yield_value = output_quantity / input_quantity
                    
                    # Record production
                    prod_data = {
                        'po_number': po_number,
                        'product': product,
                        'input_material': input_material,
                        'input_quantity': input_quantity,
                        'output_quantity': output_quantity,
                        'yield': yield_value,
                        'created_at': datetime.now().isoformat()
                    }
                    
                    # Update inventory
                    inv_data = {
                        'material': input_material,
                        'quantity': -input_quantity,  # negative because we're using the material
                        'cost': 0,  # cost is already accounted for in the purchase
                        'date': datetime.now().isoformat(),
                        'transaction_type': 'production'
                    }
                    
                    response1 = supabase.table('production').insert(prod_data).execute()
                    response2 = supabase.table('inventory_purchases').insert(inv_data).execute()
                    
                    if hasattr(response1, 'data') and hasattr(response2, 'data'):
                        st.success('Production record added successfully')
                    else:
                        st.error('Error adding production record')
                else:
                    st.error('Input and output quantities must be greater than 0')

def display_dashboard():
    st.title('Dashboard')
    st.markdown('Overview of inventory, purchases, and production metrics.')
    
    # Create tabs for different dashboard sections
    tab1, tab2 = st.tabs(["Current Inventory", "Production Metrics"])
    
    with tab1:
        # Fetch current inventory data with usage
        inventory_data = supabase.table('inventory_with_usage').select("*").execute()
        purchases = supabase.table('inventory_purchases').select("*").execute()
        
        if hasattr(inventory_data, 'data') and len(inventory_data.data) > 0:
            inventory_df = pd.DataFrame(inventory_data.data)
            purchases_df = pd.DataFrame(purchases.data) if hasattr(purchases, 'data') else pd.DataFrame()
            
            # Display current inventory levels
            st.subheader("Current Inventory Levels")
            
            # Create metrics for total inventory value and movement
            total_value = (inventory_df['current_quantity'] * inventory_df['last_purchase_price']).sum()
            total_quantity = inventory_df['current_quantity'].sum()
            total_used = inventory_df['quantity_used_in_production'].sum()
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Inventory Value", f"${total_value:,.2f}")
            with col2:
                st.metric("Total Quantity", f"{total_quantity:,.1f} lbs")
            with col3:
                st.metric("Total Used in Production", f"{total_used:,.1f} lbs")
            
            # Display inventory table
            st.markdown("### Inventory Details")
            display_df = inventory_df.copy()
            display_df['Current Value'] = display_df['current_quantity'] * display_df['last_purchase_price']
            display_df['Last Updated'] = pd.to_datetime(display_df['last_updated']).dt.strftime('%Y-%m-%d %H:%M')
            display_df['Last Purchase'] = pd.to_datetime(display_df['last_purchase_date']).dt.strftime('%Y-%m-%d')
            
            # Format the display dataframe
            display_df = display_df[[
                'material', 'current_quantity', 'quantity_used_in_production', 
                'total_purchased', 'last_purchase_price', 'Current Value', 
                'Last Updated', 'Last Purchase'
            ]].rename(columns={
                'material': 'Material',
                'current_quantity': 'Current Quantity (lbs)',
                'quantity_used_in_production': 'Used in Production (lbs)',
                'total_purchased': 'Total Purchased (lbs)',
                'last_purchase_price': 'Price/lb ($)'
            })
            
            # Format numeric columns
            display_df['Current Quantity (lbs)'] = display_df['Current Quantity (lbs)'].apply(lambda x: f"{x:,.1f}")
            display_df['Used in Production (lbs)'] = display_df['Used in Production (lbs)'].apply(lambda x: f"{x:,.1f}")
            display_df['Total Purchased (lbs)'] = display_df['Total Purchased (lbs)'].apply(lambda x: f"{x:,.1f}")
            display_df['Price/lb ($)'] = display_df['Price/lb ($)'].apply(lambda x: f"${x:,.2f}" if pd.notnull(x) else "N/A")
            display_df['Current Value'] = display_df['Current Value'].apply(lambda x: f"${x:,.2f}" if pd.notnull(x) else "N/A")
            
            st.dataframe(display_df, hide_index=True)
            
            # Create a bar chart comparing current inventory vs used in production
            st.markdown("### Inventory Usage Visualization")
            chart_data = pd.melt(
                inventory_df[['material', 'current_quantity', 'quantity_used_in_production']], 
                id_vars=['material'],
                value_vars=['current_quantity', 'quantity_used_in_production'],
                var_name='Metric',
                value_name='Quantity'
            )
            
            chart_data['Metric'] = chart_data['Metric'].map({
                'current_quantity': 'Current Inventory',
                'quantity_used_in_production': 'Used in Production'
            })
            
            inventory_chart = alt.Chart(chart_data).mark_bar().encode(
                x=alt.X('material:N', title='Material'),
                y=alt.Y('Quantity:Q', title='Quantity (lbs)'),
                color='Metric:N',
                tooltip=[
                    alt.Tooltip('material:N', title='Material'),
                    alt.Tooltip('Metric:N', title='Metric'),
                    alt.Tooltip('Quantity:Q', title='Quantity (lbs)', format=',.1f')
                ]
            ).properties(
                title='Current Inventory vs Production Usage by Material',
                width=800,
                height=400
            ).interactive()
            
            st.altair_chart(inventory_chart)
            
            # Display recent purchase history
            if not purchases_df.empty:
                st.markdown("### Recent Purchases")
                recent_purchases = purchases_df.sort_values('purchase_date', ascending=False).head(10)
                recent_purchases['purchase_date'] = pd.to_datetime(recent_purchases['purchase_date']).dt.strftime('%Y-%m-%d')
                recent_purchases['price_per_lb'] = recent_purchases['price_per_lb'].apply(lambda x: f"${x:,.2f}")
                recent_purchases['cost'] = recent_purchases['cost'].apply(lambda x: f"${x:,.2f}")
                recent_purchases['quantity'] = recent_purchases['quantity'].apply(lambda x: f"{x:,.1f}")
                
                st.dataframe(
                    recent_purchases[[
                        'purchase_date', 'material', 'quantity', 'price_per_lb', 
                        'cost', 'invoice_number'
                    ]].rename(columns={
                        'purchase_date': 'Date',
                        'material': 'Material',
                        'quantity': 'Quantity (lbs)',
                        'price_per_lb': 'Price/lb',
                        'cost': 'Total Cost',
                        'invoice_number': 'Invoice #'
                    }),
                    hide_index=True
                )
        else:
            st.info("No inventory data available")
    
    with tab2:
        # Fetch production data
        production = supabase.table('production').select("*").execute()
        
        if hasattr(production, 'data') and len(production.data) > 0:
            production_df = pd.DataFrame(production.data)
            
            # Sort by PO number
            def extract_po_number(po):
                if pd.isna(po):
                    return float('inf')  # Put NaN values at the end
                match = re.search(r'(\d+)', str(po))
                return float('inf') if match is None else int(match.group(1))
            
            production_df = production_df.sort_values(by='po_number', key=lambda x: x.map(extract_po_number))
            
            # Display metrics
            col1, col2, col3 = st.columns(3)
            
            with col1:
                avg_yield = production_df['yield'].mean()
                st.metric("Average Yield", f"{avg_yield:.1%}")
            
            with col2:
                total_input = production_df['input_quantity'].sum()
                st.metric("Total Input (lbs)", f"{total_input:,.0f}")
            
            with col3:
                total_output = production_df['output_quantity'].sum()
                st.metric("Total Output (lbs)", f"{total_output:,.0f}")
            
            # Yield trends
            st.subheader('Yield Trends')
            yield_chart = alt.Chart(production_df).mark_line(point=True).encode(
                x=alt.X('po_number:N', title='PO Number'),
                y=alt.Y('yield:Q', title='Yield %', scale=alt.Scale(domain=[0, 1])),
                color=alt.Color('product:N', title='Product'),
                tooltip=['po_number', 'product', 
                        alt.Tooltip('yield:Q', format='.1%'),
                        alt.Tooltip('input_quantity:Q', format=',.1f', title='Input (lbs)'),
                        alt.Tooltip('output_quantity:Q', format=',.1f', title='Output (lbs)')]
            ).properties(
                title='Yield Trends by Product',
                width=800,
                height=400
            ).interactive()
            
            st.altair_chart(yield_chart)
            
            # Display detailed data table
            st.subheader('Production Details')
            display_df = production_df.copy()
            display_df['yield'] = display_df['yield'].apply(lambda x: f"{x:.1%}")
            display_df['input_quantity'] = display_df['input_quantity'].apply(lambda x: f"{x:,.1f}")
            display_df['output_quantity'] = display_df['output_quantity'].apply(lambda x: f"{x:,.1f}")
            st.dataframe(
                display_df[['po_number', 'product', 'input_material', 'input_quantity', 'output_quantity', 'yield']],
                hide_index=True
            )
        else:
            st.info("No production data available")

def order_board():
    st.title('Order Board')
    st.markdown('Track and manage orders')
    
    # Fetch orders from database, ordered by delivery date
    response = supabase.table('orders').select('*').order('delivery_date').execute()
    
    if hasattr(response, 'data') and len(response.data) > 0:
        orders_df = pd.DataFrame(response.data)
        
        # Add filters
        col1, col2, col3 = st.columns(3)
        with col1:
            status_filter = st.multiselect(
                'Filter by Status',
                ['pending', 'in_production', 'completed', 'cancelled'],
                default=['pending', 'in_production']
            )
        
        with col2:
            search = st.text_input('Search PO Number')
            
        with col3:
            date_filter = st.selectbox(
                'Date Filter',
                ['All', 'Today', 'This Week', 'This Month', 'Past Due']
            )
        
        # Apply date filter
        today = pd.Timestamp.now().date()
        if date_filter == 'Today':
            orders_df = orders_df[pd.to_datetime(orders_df['delivery_date']).dt.date == today]
        elif date_filter == 'This Week':
            week_end = today + pd.Timedelta(days=7)
            orders_df = orders_df[
                (pd.to_datetime(orders_df['delivery_date']).dt.date >= today) &
                (pd.to_datetime(orders_df['delivery_date']).dt.date <= week_end)
            ]
        elif date_filter == 'This Month':
            month_end = (pd.Timestamp.now() + pd.offsets.MonthEnd(0)).date()
            orders_df = orders_df[
                (pd.to_datetime(orders_df['delivery_date']).dt.date >= today) &
                (pd.to_datetime(orders_df['delivery_date']).dt.date <= month_end)
            ]
        elif date_filter == 'Past Due':
            orders_df = orders_df[
                (pd.to_datetime(orders_df['delivery_date']).dt.date < today) &
                (orders_df['status'] != 'completed') &
                (orders_df['status'] != 'cancelled')
            ]
        
        # Filter dataframe
        filtered_df = orders_df[
            (orders_df['status'].isin(status_filter)) &
            (orders_df['po_number'].str.contains(search, case=False, na=False))
        ]
        
        # Display orders
        for _, order in filtered_df.iterrows():
            try:
                delivery_date = pd.to_datetime(order.get('delivery_date')).date() if order.get('delivery_date') else None
                po_date = pd.to_datetime(order.get('po_date')).date() if order.get('po_date') else None
                
                header = f"PO #{order['po_number']} - {order['status'].title()}"
                if delivery_date:
                    header += f" - Due: {delivery_date}"
                    is_past_due = delivery_date < today and order['status'] not in ['completed', 'cancelled']
                    if is_past_due:
                        header = f"PAST DUE - {header}"
                
                with st.expander(header):
                    col1, col2, col3, col4 = st.columns(4)
                    
                    with col1:
                        st.markdown(f"**Total Cost:** ${order['total_cost']:,.2f}")
                    
                    with col2:
                        if po_date:
                            st.markdown(f"**PO Date:** {po_date}")
                        else:
                            st.markdown("**PO Date:** Not set")
                    
                    with col3:
                        st.markdown(f"**Status:** {order['status'].title()}")
                    
                    with col4:
                        new_status = st.selectbox(
                            'Update Status',
                            ['pending', 'in_production', 'completed', 'cancelled'],
                            index=['pending', 'in_production', 'completed', 'cancelled'].index(order['status']),
                            key=f"status_{order['id']}"
                        )
                        
                        if new_status != order['status']:
                            if st.button('Update', key=f"update_{order['id']}"):
                                response = supabase.table('orders').update({'status': new_status}).eq('id', order['id']).execute()
                                if hasattr(response, 'data'):
                                    st.success('Status updated!')
                                    st.rerun()
                    
                    st.markdown("### Line Items")
                    for item in order['line_items']:
                        st.markdown(f"- {item['product']}: {item['quantity']:,.1f} lbs")
                    
                    if order.get('notes'):
                        st.markdown("### Notes")
                        st.markdown(order['notes'])
            except Exception as e:
                st.error(f"Error displaying order {order.get('po_number', 'Unknown')}: {str(e)}")
                continue
    else:
        st.info("No orders found")

# Sidebar Navigation
st.sidebar.title('Order Calculator App')
page = st.sidebar.radio('Select Page', ['Calculator', 'Inventory Tracking', 'Dashboard', 'Order Planning', 'Order Board'])

# Page routing
if page == 'Calculator':
    st.title('Order Calculator')
    st.markdown('Enter purchase order cases and existing raw materials inventory below.')
    
    # Create three columns for different product categories
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.subheader('Independent Products')
        # Ribeye and Outside Skirt
        order_inputs = {}
        order_inputs['WF Kosher Boneless Beef Ribeye Steak'] = st.number_input(
            'Ribeye Steak (cases)', 
            min_value=0, 
            step=1, 
            value=0
        )
        order_inputs['WF Kosher Beef Outside Skirt Steak'] = st.number_input(
            'Outside Skirt Steak (cases)', 
            min_value=0, 
            step=1, 
            value=0
        )
    
    with col2:
        st.subheader('Brisket Products')
        # Only input for Brisket Flat
        brisket_cases = st.number_input(
            'Brisket Flat Cut (cases)', 
            min_value=0, 
            step=1, 
            value=0
        )
        order_inputs['WF Kosher Boneless Beef Brisket Flat Cut'] = brisket_cases
        
        if brisket_cases > 0:
            # Calculate related products
            brisket_info = products['WF Kosher Boneless Beef Brisket Flat Cut']
            total_input_needed = (brisket_cases * brisket_info['avg_case_weight']) / brisket_info['yield']
            
            st.info(f"""
            From {total_input_needed:.2f} lbs of Brisket input, you will get:
            - {(total_input_needed * brisket_info['related_yields']['Stew']):.2f} lbs of Stew
            - {(total_input_needed * brisket_info['related_yields']['Grind']):.2f} lbs of Grind for blending
            """)
    
    with col3:
        st.subheader('Chuck Products')
        # Radio button to select which Chuck product to input
        chuck_product = st.radio(
            "Select Chuck product to input:",
            ['Chuck Roast', 'Short Ribs', 'Ground Beef']
        )
        
        chuck_cases = st.number_input(
            f'{chuck_product} (cases)', 
            min_value=0, 
            step=1, 
            value=0
        )
        
        if chuck_product == 'Chuck Roast':
            order_inputs['WF Kosher Boneless Beef Chuck Roast'] = chuck_cases
            if chuck_cases > 0:
                roast_info = products['WF Kosher Boneless Beef Chuck Roast']
                total_input_needed = (chuck_cases * roast_info['avg_case_weight']) / roast_info['yield']
                st.info(f"""
                From {total_input_needed:.2f} lbs of Chuck input, you will get:
                - {(total_input_needed * roast_info['related_yields']['Short Rib']):.2f} lbs of Short Ribs
                - {(total_input_needed * roast_info['related_yields']['Grind']):.2f} lbs of Grind
                """)
        
        elif chuck_product == 'Short Ribs':
            order_inputs['WF Kosher Boneless Beef Short Ribs'] = chuck_cases
            if chuck_cases > 0:
                shortrib_info = products['WF Kosher Boneless Beef Short Ribs']
                total_input_needed = (chuck_cases * shortrib_info['avg_case_weight']) / shortrib_info['yield']
                st.info(f"""
                From {total_input_needed:.2f} lbs of Chuck input, you will get:
                - {(total_input_needed * shortrib_info['related_yields']['Chuck Roast']):.2f} lbs of Chuck Roast
                - {(total_input_needed * shortrib_info['related_yields']['Grind']):.2f} lbs of Grind
                """)
        
        else:  # Ground Beef
            order_inputs['WF Kosher Ground Beef Blend of Chuck & Brisket (80/20)'] = chuck_cases
            if chuck_cases > 0:
                ground_info = products['WF Kosher Ground Beef Blend of Chuck & Brisket (80/20)']
                total_input_needed = (chuck_cases * ground_info['avg_case_weight']) / ground_info['yield']
                # Calculate related products using Chuck Roast's related yields since they share the same source
                roast_info = products['WF Kosher Boneless Beef Chuck Roast']
                st.info(f"""
                From {total_input_needed:.2f} lbs of Chuck input, you will get:
                - {(total_input_needed * roast_info['related_yields']['Short Rib']):.2f} lbs of Short Ribs
                - {(total_input_needed * 0.2734375):.2f} lbs of Chuck Roast
                """)
    
    st.subheader('Existing Raw Material Inventory (lbs)')
    col4, col5 = st.columns(2)
    with col4:
        inventory = {}
        inventory['RIBEYE'] = st.number_input('Current RIBEYE inventory', min_value=0.0, step=0.1, value=0.0)
        inventory['BRISKET'] = st.number_input('Current BRISKET inventory', min_value=0.0, step=0.1, value=0.0)
    with col5:
        inventory['2PC CHUCK'] = st.number_input('Current 2PC CHUCK inventory', min_value=0.0, step=0.1, value=0.0)
        inventory['OUTSIDE SKIRT'] = st.number_input('Current OUTSIDE SKIRT inventory', min_value=0.0, step=0.1, value=0.0)
    
    if st.button('Calculate Order'):
        results = []
        total_cost = 0
        
        # Group raw materials needed
        raw_materials_needed = {
            'RIBEYE': 0,
            'BRISKET': 0,
            '2PC CHUCK': 0,
            'OUTSIDE SKIRT': 0
        }
        
        # Define yields for raw materials
        raw_material_yields = {
            'RIBEYE': 0.75,  # From Ribeye product
            'BRISKET': 0.4551971326,  # From Brisket Flat
            '2PC CHUCK': 0.2734375,  # Using Chuck Roast yield as base
            'OUTSIDE SKIRT': 0.85  # From Outside Skirt product
        }
        
        for product, cases in order_inputs.items():
            if cases > 0:
                info = products[product]
                finished_lbs = cases * info['avg_case_weight']
                required_raw = finished_lbs / info['yield']
                raw_materials_needed[info['raw_material']] += required_raw
        
        # Calculate new orders needed
        for material, required in raw_materials_needed.items():
            if required > 0:
                current_inv = inventory.get(material, 0)
                # Convert existing inventory to raw material equivalent
                current_inv_raw = current_inv / raw_material_yields[material]
                order_needed = max(required - current_inv_raw, 0)
                if order_needed > 0:
                    results.append({
                        'Raw Material': material,
                        'Total Required (lbs)': round(required, 2),
                        'Current Inventory (finished lbs)': current_inv,
                        'Current Inventory (raw lbs)': round(current_inv_raw, 2),
                        'New Order Needed (lbs)': round(order_needed, 2)
                    })
        
        if results:
            st.write(pd.DataFrame(results))
        else:
            st.info('Current inventory is sufficient for this order.')

elif page == 'Inventory Tracking':
    inventory_tracking()
    
elif page == 'Dashboard':
    display_dashboard()
    
elif page == 'Order Planning':
    order_planning()
    
elif page == 'Order Board':
    order_board()

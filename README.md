<b>QERP</b> <br>
A lightweight ERP system built for small precision manufacturing operations. Developed to replace paper-based job tracking at a real machine shop, QERP is a web-based system for managing the full production lifecycle -- from customer orders to shop floor execution to quality inspections.<br>
Built with Flask and PostgreSQL. Designed with ISO 9001:2015 compliance in mind.<br>
<br>
<b>Modules</b><br>

<ul><li>Work Orders - create, route, and track jobs from order to shipment
<li>Shop Floor - role-based operation execution with real-time status tracking
<li>Inspections - FAI, AQL, in-process, and final inspection recording with NCR/CAPA workflow
<li>Parts - part master data with drawing revision control
<li>Customers & Suppliers - contact management and approved supplier list
<li>Reports - on-time delivery, WIP, production summary, NCR trending
<li>User Management - 7-tier role-based access control</ul>

<b>Stack</b><br>
Python, Flask, PostgreSQL, Jinja2, Bootstrap 5<br><br>
<b>ISO 9001:2015</b><br>
Clauses 7.5, 8.2, 8.4, 8.5, 8.6, 8.7, 9.1, 10.2
<br><br>
<b>Setup:</b><br>
Clone the repo<br>
Create a PostgreSQL database and run qerp_schema.sql<br>
Copy .env.example to .env and add your database URL and secret key<br>
pip install -r requirements.txt<br>
python app.py<br>
<hr>
dedicated to Quinn

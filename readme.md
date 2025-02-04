# Project Setup Guide

## **Getting Started**

Follow these steps to set up and run the project locally.

### **1. Clone the Repository**

```bash
git clone <repository_url>
cd <repository_name>
```

### **2. Switch to the Master Branch**

```bash
git checkout master
```

### **3. Create and Activate a Virtual Environment**

#### **For macOS/Linux**

```bash
python3 -m venv env
source env/bin/activate
```

#### **For Windows**

```bash
python -m venv env
env\Scripts\activate
```

### **4. Install Dependencies**

```bash
pip install -r requirements.txt
```

### **5. Apply Migrations**

```bash
python manage.py makemigrations
python manage.py migrate
```

### **6. Run the Development Server**

```bash
python manage.py runserver
```

The application will be available at: **[http://127.0.0.1:8000/](http://127.0.0.1:8000/)**

---

### **Additional Commands**

* **Deactivate the virtual environment:**
  ```bash
  deactivate
  ```
* **Check installed dependencies:**
  ```bash
  pip freeze
  ```
* **Run tests (if applicable):**
  ```bash
  python manage.py test
  ```

---

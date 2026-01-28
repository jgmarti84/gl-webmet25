# README for Radar API Project

# Radar API

This project is a Django application designed to provide an API for radar data. It includes various endpoints for accessing products and stations related to radar information.

## Project Structure

The project consists of the following files and directories:

- `__init__.py`: Indicates that the directory should be treated as a Python package.
- `admin.py`: Used to register models with the Django admin site.
- `apps.py`: Contains the configuration for the Django application.
- `models.py`: Defines the data models for the application.
- `views.py`: Contains the view functions that handle requests and return responses.
- `urls.py`: Defines the URL routing for the application.
- `serializers.py`: Used for serializing and deserializing data for APIs.
- `forms.py`: Defines forms for handling user input and validation.
- `tests.py`: Contains test cases for the application.
- `migrations/`: Directory containing migration files for database schema changes.
- `templates/radar_api/index.html`: HTML template for rendering the index page.
- `static/radar_api/css/styles.css`: CSS styles for the application.

## Setup Instructions

1. **Clone the repository**:
   ```
   git clone <repository-url>
   cd radar_api
   ```

2. **Install dependencies**:
   ```
   pip install -r requirements.txt
   ```

3. **Run migrations**:
   ```
   python manage.py migrate
   ```

4. **Start the development server**:
   ```
   python manage.py runserver
   ```

5. **Access the API**:
   Open your browser and navigate to `http://127.0.0.1:8000/api/products/` or `http://127.0.0.1:8000/api/stations/` to access the respective endpoints.

## Usage

This API can be used to retrieve radar products and station information. Ensure that you have the necessary permissions and authentication if required.

## Contributing

Contributions are welcome! Please submit a pull request or open an issue for any enhancements or bug fixes.
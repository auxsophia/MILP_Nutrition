#!/bin/bash

# Script to create and activate a virtual environment called 'venv'

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null
then
    echo "Python 3 is not installed. Please install Python 3."
    exit 1
fi

# Create virtual environment called 'venv'
echo "Creating virtual environment 'venv'..."
python3 -m venv venv

# Check if virtual environment was created successfully
if [ -d "venv" ]; then
    echo "Virtual environment 'venv' created successfully."
else
    echo "Failed to create virtual environment 'venv'."
    exit 1
fi

# Activate the virtual environment
echo "Activating virtual environment... source venv/bin/activate"
echo "source venv/bin/activate"
source venv/bin/activate

# Check if activation was successful
if [[ "$VIRTUAL_ENV" == "" ]]; then
    echo "Failed to activate virtual environment."
    exit 1
else
    echo "Virtual environment 'venv' activated."
fi

# Check for requirements.txt and install dependencies if it exists
if [ -f "requirements.txt" ]; then
    echo "requirements.txt found. Installing dependencies..."
    pip install -r requirements.txt
    if [ $? -eq 0 ]; then
        echo "Dependencies installed successfully."
    else
        echo "Failed to install dependencies."
    fi
else
    echo "No requirements.txt found. Skipping dependency installation."
fi

# Keep the virtual environment activated for further use in the terminal
echo "Virtual environment 'venv' is ready and active. You can now use it."
echo "To deactivate, type 'deactivate'."

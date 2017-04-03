#!/usr/bin/env python3
#
# Copyright (C) 2017 Chris Blake <chris@servernetworktech.com>
#
from frontend import app
import os

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

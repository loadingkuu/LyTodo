
运行：
  1) pip install PySide6,requests
  2) cd todo_app
  3) python app.py

打包：python -- 3.12
  python -m PyInstaller ^
  --noconsole ^
  --onedir ^
  --name LyTodo ^
  --clean ^
  --collect-all requests ^
  --collect-all certifi ^
  app.py


特征：
  暂无

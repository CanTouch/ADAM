"""Tool registry: name -> function, plus the schemas sent to the model."""
from tools import browser, desktop, files, memory, vault, web

FUNCTIONS = {
    "list_files": files.list_files,
    "read_file": files.read_file,
    "search_files": files.search_files,
    "move_file": files.move_file,
    "delete_file": files.delete_file,
    "write_note": files.write_note,
    "open_url": browser.open_url,
    "use_current_tab": browser.use_current_tab,
    "click": browser.click,
    "fill_form": browser.fill_form,
    "get_page_text": browser.get_page_text,
    "screenshot": browser.screenshot,
    "web_search": web.web_search,
    "read_note": vault.read_note,
    "search_vault": vault.search_vault,
    "open_app": desktop.open_app,
    "open_path": desktop.open_path,
    "list_windows": desktop.list_windows,
    "focus_window": desktop.focus_window,
    "minimize_window": desktop.minimize_window,
    "close_window": desktop.close_window,
    "remember": memory.remember,
    "forget": memory.forget,
}


def _tool(name, description, /, **params):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {k: {"type": "string", "description": v} for k, v in params.items()},
                "required": list(params),
            },
        },
    }


SCHEMAS = [
    _tool("list_files", "List the contents of a folder.", path="Folder path"),
    _tool("read_file", "Read a text file.", path="File path"),
    _tool("search_files", "Find files and folders whose name contains the query.",
          query="Part of the file name", root="Folder to search under"),
    _tool("move_file", "Move or rename a file or folder. Never overwrites.",
          src="Current path", dst="New path or destination folder"),
    _tool("delete_file", "Send a file or folder to the Recycle Bin / Trash.", path="Path to delete"),
    _tool("write_note", "Write a markdown note to the AgentSandbox notes folder. Appends if the file exists.",
          content="Markdown content", filename="File name, e.g. summary.md"),
    _tool("open_url", "Open a web page in the user's Google Chrome, in Adam's tab (labelled Adam).",
          url="URL to open"),
    _tool("use_current_tab", "Make the tab the user is looking at in Chrome Adam's tab, "
          "so the other browser tools act on it."),
    _tool("click", "Click an element in Adam's tab.",
          selector="text=Visible text, or a CSS selector like #submit or a[href*='docs']"),
    _tool("fill_form", "Type a value into an input field in Adam's tab. Does not submit.",
          selector="CSS selector of the input, e.g. input[name=q]", value="Text to enter"),
    _tool("get_page_text", "Read the visible text of the page in Adam's tab."),
    _tool("screenshot", "Capture Adam's tab and show it to the user."),
    _tool("web_search", "Search the web and return the top results.", query="Search query"),
    _tool("read_note", "Read a note from the user's Obsidian vault (read-only).",
          filename="Note name or path inside the vault"),
    _tool("search_vault", "Search note titles and contents in the Obsidian vault.",
          query="Text to find"),
    _tool("open_app", "Open an installed desktop app by name, e.g. Files, Calculator, Obsidian.",
          name="App name"),
    _tool("open_path", "Open a file or folder on screen in its normal program.", path="File or folder path"),
    _tool("list_windows", "List open windows with their ids and titles."),
    _tool("focus_window", "Bring a window to the front.", window="Window title (or part of it) or id"),
    _tool("minimize_window", "Minimize a window.", window="Window title (or part of it) or id"),
    _tool("close_window", "Close a window. The app may ask to save first.",
          window="Window title (or part of it) or id"),
    _tool("remember", "Save a lasting fact about the user to your memory, kept across restarts.",
          fact="One short fact, e.g. 'Prefers dark mode' or 'Works at KuppeLabs'"),
    _tool("forget", "Remove remembered facts that contain this text.", text="Text to match"),
]

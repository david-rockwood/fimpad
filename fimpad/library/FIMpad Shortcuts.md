# FIMpad Shortcuts



## Application shortcuts



### File menu shortcuts

Alt+T - New Tab

Alt+O - Open

Alt+S - Save

Alt+A - Save As

Alt+C - Close Tab

Alt+Q - Quit



### Edit menu shortcuts

Alt+U - Undo

Alt+R - Redo

Ctrl+X - Cut

Ctrl+C - Copy

Ctrl+V - Paste

Del - Delete

Ctrl+/ - Select All

Alt+/ - Find & Replace

Alt+. - Regex & Replace

Alt+; - Open Settings Window



### Toggle menu shortcuts

Ctrl+Alt+W - Toggle Word Wrap

Ctrl+Alt+F - Toggle Follow Stream

Ctrl+Alt+N - Toggle Line Numbering

Ctrl+Alt+S - Toggle Spellchecking



### AI menu shortcuts

Ctrl+Shift+G - Generate

Ctrl+Shift+R - Repeat Last FIM

Ctrl+Shift+P - Paste Last FIM Tag

Ctrl+Shift+I - Interrupt Stream

Ctrl+Shift+V - Validate Tags

Ctrl+Shift+L - Show Log



### Tab switching shortcuts

Alt+(a number key) - Switch To Tab

Ctrl+PageUp - Switch Left 1 Tab

Ctrl+PageDown - Switch 1 Tab Right



## Text editing shortcuts provided by Tk



### Mouse bindings

Button-1 click - Move insertion cursor to clicked char, focus the widget, clear selection.

Button-1 drag - Select text from insertion point to current mouse.

Button-1 double-click - Select word under mouse; insertion at word start.

Button-1 drag after double-click - Extend selection in word units.

Button-1 triple-click - Select line under mouse; insertion at line start.

Button-1 drag after triple-click - Extend selection in line units.

Shift + Button-1 drag - Adjust nearest end of selection.

Ctrl + Button-1 click - Move insertion cursor without touching selection.

Button-2 drag - Scroll view (like grab and drag).

Button-2 click (no drag) - Insert current selection at mouse position.

Insert key - Insert current selection at insertion cursor.

Button-1 drag out of widget - Auto-scroll while dragging.



### Cursor movement / navigation

Left / Right Arrow Keys - Move cursor one character left/right and clear selection.

Shift + Left / Right Arrow Keys - Move cursor and extend selection by one char.

Ctrl + Left / Right Arrow Keys - Move by word.

Ctrl + Shift + Left / Right Arrow Keys - Move by word and extend selection.

Ctrl+B / Ctrl+F - Same as Left / Right.

Alt+B / Alt+F - Same as Ctrl+Left / Ctrl+Right.

Up / Down Arrow Keys - Move cursor one line up/down, clear selection.

Shift + Up / Down Arrow Keys - Move and extend selection by a line.

Ctrl + Up / Down Arrow Keys - Move by paragraph (blocks separated by blank lines).

Ctrl + Shift + Up / Down Arrow Keys - Move by paragraph and extend selection.

Ctrl+P / Ctrl+N - Same as Up / Down.

PageDown (Next) / PageUp (Prior) - Move cursor by one horizontal screen, clear selection.

Shift + PageDown / PageUp - Move by horizontal screen and extend selection.

Ctrl+PageDown / Ctrl+PageUp - Scroll view right/left by one horizontal screen without moving cursor or selection.

Home / Ctrl+A - Move cursor to start of line, clear selection.

Shift+Home / Ctrl+A - Same, but extend selection.

End / Ctrl+E - Move cursor to end of line, clear selection.

Shift+End / Ctrl+E - Same, but extend selection.

Ctrl+Home / Alt+< - Move cursor to start of text, clear selection.

Ctrl+Shift+Home - Same, but extend selection.

Ctrl+End / Alt+> - Move cursor to end of text, clear selection.

Ctrl+Shift+End - Same, but extend selection.



### Selection / mark control

Ctrl+Space - Set selection anchor at insertion cursor, but don’t change current selection.

Ctrl+Shift+Space - Adjust selection from anchor to insertion cursor (or create selection if none).

Ctrl+/ - Select entire contents of the document.

Ctrl+\ - Clear any selection in the document.



### Cut / copy / paste (Tk / Emacs style)

Ctrl+W - Cut: copy selection to clipboard and delete it.

Ctrl+Y - Paste from clipboard at insertion cursor.



### Deletion / killing

Delete - If selection exists: delete it. Otherwise: delete char right of cursor.

Backspace / Ctrl+H - If selection exists: delete it. Otherwise: delete char left of cursor.

Ctrl+D - Delete char right of cursor.

Ctrl+K - Kill from cursor to end of line; if already at end of line, delete the newline.

Ctrl+X - Cut whatever is selected in the text document.



### Emacs-like unusual operations

Ctrl+O - “Open line”: insert a newline before the cursor without moving the cursor.

Ctrl+T - Transpose the character left of the carat with the character right of the carat.




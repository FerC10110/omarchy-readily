import QtQuick
import qs.Commons

// Temporary (Task 11): shows what the panel read, so the flow can be checked
// before the real list exists. Replaced in Task 12.
Item {
  id: view
  property var host: null
  readonly property Item focusItem: keys
  implicitHeight: label.implicitHeight

  Item {
    id: keys
    focus: true
    Keys.onPressed: function(event) {
      if (event.key === Qt.Key_Escape) {
        view.host.close()
        event.accepted = true
      }
    }
  }

  Text {
    id: label
    width: parent.width
    wrapMode: Text.WordWrap
    text: view.host ? (view.host.payload.sections || []).length + " sections in " + view.host.payload.folder
      + (view.host.notice !== "" ? "\n" + view.host.notice : "") : ""
    color: view.host ? view.host.foreground : Color.foreground
    font.pixelSize: Style.font.body
  }
}

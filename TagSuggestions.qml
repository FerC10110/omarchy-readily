import QtQuick
import qs.Commons

// The #tag autocomplete list shared by the list and save views.
Column {
  id: root

  property var suggestions: []
  property int current: 0
  property color foreground: Color.foreground
  property string fontFamily: Style.font.family

  signal picked(int index)

  visible: suggestions.length > 0
  spacing: Style.space(2)

  Repeater {
    model: root.suggestions

    Rectangle {
      required property var modelData
      required property int index
      width: parent.width
      height: suggestionText.implicitHeight + Style.space(6)
      radius: Style.cornerRadius
      color: index === root.current ? Style.selectionFillFor(root.foreground, Color.accent) : "transparent"

      Text {
        id: suggestionText
        x: Style.space(8)
        anchors.verticalCenter: parent.verticalCenter
        text: "#" + modelData.name + "   " + modelData.count
        textFormat: Text.PlainText
        color: root.foreground
        font.family: root.fontFamily
        font.pixelSize: Style.font.bodySmall
      }

      MouseArea {
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        onClicked: root.picked(index)
      }
    }
  }
}

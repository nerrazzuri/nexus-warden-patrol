// 外审 1.1 第 4 轮 #5：拍的人脸照片读出来就删，不留在手机缓存里。
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:nexwar_patrol/ui/face_enrol.dart';

void main() {
  test('读出来就删：拍的那张、插件留的原图缩图都删，别的文件不动', () async {
    final dir = Directory.systemTemp.createTempSync('selfie');
    addTearDown(() => dir.deleteSync(recursive: true));
    final shot = File('${dir.path}/scaled_abc.jpg')..writeAsBytesSync(<int>[1, 2, 3]);
    final orig = File('${dir.path}/image_picker_123.jpg')..writeAsBytesSync(<int>[9]);
    final other = File('${dir.path}/keep.txt')..writeAsStringSync('x');
    final bytes = await readAndForget(shot.path);
    expect(bytes, <int>[1, 2, 3]);
    expect(shot.existsSync(), isFalse);
    expect(orig.existsSync(), isFalse);
    expect(other.existsSync(), isTrue);
  });

  test('读不出来也删', () async {
    final dir = Directory.systemTemp.createTempSync('selfie');
    addTearDown(() => dir.deleteSync(recursive: true));
    await expectLater(readAndForget('${dir.path}/image_picker_gone.jpg'), throwsA(isA<FileSystemException>()));
    final left = File('${dir.path}/image_picker_left.jpg')..writeAsBytesSync(<int>[1]);
    await expectLater(readAndForget('${dir.path}/missing.jpg'), throwsA(isA<FileSystemException>()));
    expect(left.existsSync(), isFalse);
  });
}

import 'dart:convert';
import 'dart:io';
import 'package:flutter/foundation.dart' show kIsWeb; // 웹 여부 확인용
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:intl/intl.dart';
import 'package:path_provider/path_provider.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:record/record.dart';
import 'package:table_calendar/table_calendar.dart';

void main() {
  runApp(const MyApp());
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Voice To-Do',
      theme: ThemeData(primarySwatch: Colors.blue),
      home: const TodoHomePage(),
    );
  }
}

class TodoHomePage extends StatefulWidget {
  const TodoHomePage({super.key});

  @override
  State<TodoHomePage> createState() => _TodoHomePageState();
}

class _TodoHomePageState extends State<TodoHomePage> {
  // --- 변수 설정 ---
  final AudioRecorder _audioRecorder = AudioRecorder();
  bool _isRecording = false;
  bool _isLoading = false; 
  
  // [중요] 여기에 본인의 CloudType 서버 주소를 넣으세요! (끝에 / 빼고)
  final String baseUrl = 'https://port-0-voice-todo-server-milo3zb6ebdebc3e.sel3.cloudtype.app'; 

  DateTime _focusedDay = DateTime.now();
  DateTime? _selectedDay;
  List<dynamic> _tasks = []; 

  @override
  void initState() {
    super.initState();
    _selectedDay = _focusedDay;
    _fetchTasks(); 
  }

  // --- [1] 서버에서 목록 가져오기 ---
  Future<void> _fetchTasks() async {
    try {
      final response = await http.get(Uri.parse('$baseUrl/tasks'));
      if (response.statusCode == 200) {
        setState(() {
          _tasks = jsonDecode(utf8.decode(response.bodyBytes));
        });
      }
    } catch (e) {
      print("목록 불러오기 실패: $e");
    }
  }

  // --- [2] 녹음 시작 (웹/윈도우 호환) ---
  Future<void> _startRecording() async {
    // 권한 체크
    var status = await Permission.microphone.request();
    if (status != PermissionStatus.granted) {
        print("마이크 권한 거부됨");
        return;
    }

    // 경로 설정 (웹에서는 경로가 필요 없음)
    String? path;
    if (!kIsWeb) {
      final directory = await getApplicationDocumentsDirectory();
      path = '${directory.path}/voice_temp.wav';
    }

    if (await _audioRecorder.hasPermission()) {
      // [중요] 웹일 때는 인코더 설정을 비워서 브라우저가 알아서 하게 둠
      // 윈도우일 때는 WAV로 고정
      final config = RecordConfig(
        encoder: kIsWeb ? AudioEncoder.aacLc : AudioEncoder.wav, 
      );
      
      // 웹에서는 path에 ''(빈문자열)을 넣어야 메모리에 저장됨
      await _audioRecorder.start(config, path: path ?? '');
      
      setState(() => _isRecording = true);
      print("녹음 시작됨");
    }
  }

  // --- [3] 녹음 중지 및 분석 요청 ---
  Future<void> _stopAndAnalyze() async {
    final path = await _audioRecorder.stop();
    setState(() => _isRecording = false);

    // 웹에서는 path가 null이거나 blob URL일 수 있음
    if (path == null) return;

    setState(() => _isLoading = true);

    try {
      var request = http.MultipartRequest('POST', Uri.parse('$baseUrl/analyze-voice'));
      
      if (kIsWeb) {
        // 웹: 네트워크에서 파일 가져오듯 처리
        var blob = await http.get(Uri.parse(path));
        request.files.add(http.MultipartFile.fromBytes(
          'file',
          blob.bodyBytes,
          filename: 'voice.webm', // 웹은 보통 webm이나 mp4
        ));
      } else {
        // 윈도우/앱: 로컬 파일 경로 사용
        request.files.add(await http.MultipartFile.fromPath('file', path));
      }

      var streamedResponse = await request.send();
      var response = await http.Response.fromStream(streamedResponse);

      if (response.statusCode == 200) {
        var data = jsonDecode(utf8.decode(response.bodyBytes));
        if (mounted) _showConfirmDialog(data);
      } else {
        if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text("분석 실패")));
      }
    } catch (e) {
      print("오류: $e");
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text("서버 연결 오류")));
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  // --- [4] 확인 팝업 및 최종 저장 ---
  void _showConfirmDialog(Map<String, dynamic> data) {
    TextEditingController titleController = TextEditingController(text: data['suggested_title']);
    String? parsedDate = data['parsed_date'];
    DateTime? dateObj = parsedDate != null ? DateTime.parse(parsedDate) : null;

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      builder: (context) {
        return Padding(
          padding: EdgeInsets.only(
            bottom: MediaQuery.of(context).viewInsets.bottom + 20, 
            top: 20, left: 20, right: 20
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text("이렇게 저장할까요?", style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
              const SizedBox(height: 10),
              TextField(
                controller: titleController,
                decoration: const InputDecoration(labelText: "할 일 내용"),
              ),
              const SizedBox(height: 10),
              Row(
                children: [
                  const Icon(Icons.calendar_today, size: 16),
                  const SizedBox(width: 8),
                  Text(dateObj != null 
                    ? DateFormat('yyyy년 MM월 dd일 HH:mm').format(dateObj) 
                    : "날짜 정보 없음 (오늘로 설정됨)"),
                ],
              ),
              const SizedBox(height: 20),
              Row(
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  TextButton(onPressed: () => Navigator.pop(context), child: const Text("취소")),
                  ElevatedButton(
                    onPressed: () {
                      _saveTask(titleController.text, dateObj);
                      Navigator.pop(context);
                    },
                    child: const Text("저장"),
                  ),
                ],
              )
            ],
          ),
        );
      },
    );
  }

  Future<void> _saveTask(String title, DateTime? date) async {
    try {
      await http.post(
        Uri.parse('$baseUrl/tasks'),
        headers: {"Content-Type": "application/json"},
        body: jsonEncode({
          "title": title,
          "due_date": date?.toIso8601String(),
          "description": "음성 입력됨"
        }),
      );
      _fetchTasks();
    } catch (e) {
      print("저장 실패: $e");
    }
  }

  // --- 화면 그리기 ---
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text("Voice To-Do List")),
      body: Column(
        children: [
          TableCalendar(
            firstDay: DateTime.utc(2020, 10, 16),
            lastDay: DateTime.utc(2030, 3, 14),
            focusedDay: _focusedDay,
            selectedDayPredicate: (day) => isSameDay(_selectedDay, day),
            onDaySelected: (selectedDay, focusedDay) {
              setState(() {
                _selectedDay = selectedDay;
                _focusedDay = focusedDay;
              });
            },
            calendarFormat: CalendarFormat.week,
          ),
          const Divider(),
          Expanded(
            child: _isLoading 
              ? const Center(child: CircularProgressIndicator()) 
              : ListView.builder(
                  itemCount: _tasks.length,
                  itemBuilder: (context, index) {
                    final task = _tasks[index];
                    final date = task['due_date'] != null 
                      ? DateTime.parse(task['due_date']) 
                      : null;
                    return ListTile(
                      leading: Checkbox(
                        value: task['is_completed'],
                        onChanged: (bool? value) async {
                           // 완료 기능 구현 필요
                        },
                      ),
                      title: Text(task['title']),
                      subtitle: date != null 
                        ? Text(DateFormat('MM/dd HH:mm').format(date)) 
                        : null,
                    );
                  },
                ),
          ),
        ],
      ),
      // [수정됨] 아이폰 터치를 위해 LongPress 삭제하고 클릭(onPressed)으로 변경
      floatingActionButton: FloatingActionButton(
        backgroundColor: _isRecording ? Colors.red : Colors.blue,
        onPressed: () {
          if (_isRecording) {
            _stopAndAnalyze();
          } else {
            _startRecording();
          }
        },
        child: Icon(_isRecording ? Icons.stop : Icons.mic),
      ),
      floatingActionButtonLocation: FloatingActionButtonLocation.centerFloat,
    );
  }
}
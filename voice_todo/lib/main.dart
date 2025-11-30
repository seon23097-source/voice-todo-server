import 'dart:convert';
import 'dart:io';
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
  bool _isLoading = false; // 서버 분석 중 로딩
  
  // 서버 주소 (윈도우 시뮬레이터 기준)
  // 안드로이드 에뮬레이터라면 'http://10.0.2.2:8000' 으로 바꿔야 함
  final String baseUrl = 'http://127.0.0.1:8000'; 

  DateTime _focusedDay = DateTime.now();
  DateTime? _selectedDay;
  List<dynamic> _tasks = []; // 할 일 목록

  @override
  void initState() {
    super.initState();
    _selectedDay = _focusedDay;
    _fetchTasks(); // 앱 켜지면 목록 불러오기
  }

  // --- [1] 서버에서 목록 가져오기 (GET) ---
  Future<void> _fetchTasks() async {
    try {
      final response = await http.get(Uri.parse('$baseUrl/tasks'));
      if (response.statusCode == 200) {
        setState(() {
          // 한글 깨짐 방지 utf8.decode
          _tasks = jsonDecode(utf8.decode(response.bodyBytes));
        });
      }
    } catch (e) {
      print("목록 불러오기 실패: $e");
    }
  }

  // --- [2] 녹음 시작 ---
    Future<void> _startRecording() async {
    // 권한 체크
    var status = await Permission.microphone.request();
    if (status != PermissionStatus.granted) {
        print("마이크 권한 거부됨");
        return;
    }

    final directory = await getApplicationDocumentsDirectory();
    
    // [변경 1] 확장자를 .wav로 변경 (호환성 최고)
    final path = '${directory.path}/voice_temp.wav';

    if (await _audioRecorder.hasPermission()) {
      // [변경 2] 인코더를 wav(pcm16bit)로 설정
      const config = RecordConfig(
        encoder: AudioEncoder.wav, 
      );
      
      await _audioRecorder.start(config, path: path);
      setState(() => _isRecording = true);
      print("녹음 시작: $path"); // 경로가 어딘지 로그로 확인
    }
    
    // _startRecording 함수 안쪽
    if (await _audioRecorder.hasPermission()) {
    // wav 설정 (윈도우 호환성 최고)
    const config = RecordConfig(encoder: AudioEncoder.wav);
    
    await _audioRecorder.start(config, path: path);
    setState(() => _isRecording = true);
    
    // ★ 이 로그를 확인하세요!
    print("녹음 파일 저장 위치: $path"); 
    }
  }

  // --- [3] 녹음 중지 및 분석 요청 (POST /analyze-voice) ---
  Future<void> _stopAndAnalyze() async {
    final path = await _audioRecorder.stop();
    setState(() => _isRecording = false);

    if (path == null) return;

    setState(() => _isLoading = true); // 로딩 시작

    try {
      // 파일 업로드
      var request = http.MultipartRequest('POST', Uri.parse('$baseUrl/analyze-voice'));
      request.files.add(await http.MultipartFile.fromPath('file', path));

      var streamedResponse = await request.send();
      var response = await http.Response.fromStream(streamedResponse);

      if (response.statusCode == 200) {
        var data = jsonDecode(utf8.decode(response.bodyBytes));
        // 분석 성공하면 확인 팝업 띄우기
        _showConfirmDialog(data);
      } else {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text("분석 실패")));
      }
    } catch (e) {
      print("오류: $e");
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text("서버 연결 오류")));
    } finally {
      setState(() => _isLoading = false); // 로딩 끝
    }
  }

  // --- [4] 확인 팝업 및 최종 저장 (POST /tasks) ---
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

  // 최종 저장 요청
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
      _fetchTasks(); // 목록 새로고침
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
          // 1. 달력
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
            calendarFormat: CalendarFormat.week, // 주간 달력으로 보기
          ),
          const Divider(),
          // 2. 할 일 리스트
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
                          // 완료 상태 변경 API 호출 (숙제: PATCH 구현해보기)
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
      // 3. 음성 입력 버튼
      floatingActionButton: GestureDetector(
        onLongPress: _startRecording, // 꾹 누르면 녹음 시작
        onLongPressUp: _stopAndAnalyze, // 떼면 분석 시작
        child: FloatingActionButton(
          backgroundColor: _isRecording ? Colors.red : Colors.blue,
          onPressed: () {
            // 짧게 누르면 안내 메시지
            ScaffoldMessenger.of(context).showSnackBar(
              const SnackBar(content: Text("버튼을 꾹 눌러서 말해보세요!")),
            );
          },
          child: Icon(_isRecording ? Icons.mic : Icons.mic_none),
        ),
      ),
      floatingActionButtonLocation: FloatingActionButtonLocation.centerFloat,
    );
  }
}
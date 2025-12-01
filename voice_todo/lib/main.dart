import 'dart:convert';
import 'dart:io';
import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:intl/intl.dart';
import 'package:intl/date_symbol_data_local.dart'; // 한국어 날짜 포맷 지원
import 'package:path_provider/path_provider.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:record/record.dart';
import 'package:table_calendar/table_calendar.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await initializeDateFormatting(); // 한국어 달력 설정을 위해 필수
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

  // [중요] 본인의 CloudType 서버 주소로 교체하세요!
  final String baseUrl = 'https://port-0-voice-todo-server-milo3zb6ebdebc3e.sel3.cloudtype.app'; 

  DateTime _focusedDay = DateTime.now();
  DateTime _selectedDay = DateTime.now(); // 선택된 날짜 (기본: 오늘)
  List<dynamic> _allTasks = []; // 전체 할 일 목록

  @override
  void initState() {
    super.initState();
    _fetchTasks();
  }

  // --- [1] 서버에서 목록 가져오기 ---
  Future<void> _fetchTasks() async {
    try {
      final response = await http.get(Uri.parse('$baseUrl/tasks'));
      if (response.statusCode == 200) {
        setState(() {
          _allTasks = jsonDecode(utf8.decode(response.bodyBytes));
        });
      }
    } catch (e) {
      print("목록 로드 실패: $e");
    }
  }

  // --- [2] 날짜별 필터링 (선택한 날짜의 할 일만 보여줌) ---
  List<dynamic> _getTasksForDay(DateTime day) {
    return _allTasks.where((task) {
      if (task['due_date'] == null) return false;
      // 서버 날짜(String)를 객체로 변환
      DateTime taskDate = DateTime.parse(task['due_date']);
      // 년, 월, 일이 같은지 비교
      return isSameDay(taskDate, day);
    }).toList();
  }

  // --- [3] 삭제 기능 (Swipe) ---
  Future<void> _deleteTask(int id) async {
    setState(() {
      _allTasks.removeWhere((t) => t['id'] == id);
    });

    try {
      await http.delete(Uri.parse('$baseUrl/tasks/$id'));
    } catch (e) {
      print("삭제 실패: $e");
      _fetchTasks(); // 실패 시 복구
    }
  }

  // --- [4] 수정 기능 (Dialog) ---
  Future<void> _editTask(Map<String, dynamic> task) async {
    TextEditingController titleController = TextEditingController(text: task['title']);
    DateTime currentDate = DateTime.parse(task['due_date']);

    await showDialog(
      context: context,
      builder: (context) {
        return AlertDialog(
          title: const Text("할 일 수정"),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: titleController, 
                decoration: const InputDecoration(labelText: "내용")
              ),
              const SizedBox(height: 10),
              ElevatedButton(
                onPressed: () async {
                  // 날짜 선택
                  final pickedDate = await showDatePicker(
                    context: context,
                    initialDate: currentDate,
                    firstDate: DateTime(2020),
                    lastDate: DateTime(2030),
                  );
                  if (pickedDate != null) {
                    // 시간 선택
                    final pickedTime = await showTimePicker(
                      context: context,
                      initialTime: TimeOfDay.fromDateTime(currentDate),
                    );
                    
                    if (pickedTime != null) {
                      currentDate = DateTime(
                        pickedDate.year, pickedDate.month, pickedDate.day,
                        pickedTime.hour, pickedTime.minute
                      );
                    }
                  }
                },
                child: const Text("날짜/시간 변경"),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context), 
              child: const Text("취소")
            ),
            ElevatedButton(
              onPressed: () {
                _updateTaskInfo(task['id'], titleController.text, currentDate);
                Navigator.pop(context);
              },
              child: const Text("수정 완료"),
            ),
          ],
        );
      },
    );
  }

  // 수정 요청 API
  Future<void> _updateTaskInfo(int id, String title, DateTime date) async {
    // 1. 서버에 전송하기 위해 기존 데이터를 찾음
    final index = _allTasks.indexWhere((t) => t['id'] == id);
    if (index == -1) return;

    // 2. 임시 업데이트 (화면 갱신)
    setState(() {
      _allTasks[index]['title'] = title;
      _allTasks[index]['due_date'] = date.toIso8601String();
    });

    // 3. 꼼수: PATCH API가 없으면 기존 할일을 삭제하고 새로 만듦 (가장 쉬운 구현)
    // 정석은 백엔드에 수정 API를 만드는 것이지만, 일단 삭제 -> 생성으로 처리
    try {
        await http.delete(Uri.parse('$baseUrl/tasks/$id'));
        await http.post(
          Uri.parse('$baseUrl/tasks'),
          headers: {"Content-Type": "application/json"},
          body: jsonEncode({
            "title": title,
            "due_date": date.toIso8601String(),
            "description": "수정됨"
          }),
        );
        _fetchTasks(); // ID 재발급을 위해 새로고침
    } catch(e) {
        print("수정 실패: $e");
    }
  }

  // --- [5] 완료 체크 (Checkbox) ---
  Future<void> _toggleTaskStatus(int id, bool currentStatus) async {
    setState(() {
      final index = _allTasks.indexWhere((t) => t['id'] == id);
      if (index != -1) {
        _allTasks[index]['is_completed'] = !currentStatus;
      }
    });

    try {
      await http.patch(
        Uri.parse('$baseUrl/tasks/$id?is_completed=${!currentStatus}'),
      );
    } catch (e) {
      _fetchTasks();
    }
  }

  // --- [6] 음성 녹음 관련 로직 ---
  Future<void> _startRecording() async {
    if (await Permission.microphone.request().isGranted) {
      String? path;
      if (!kIsWeb) {
        final dir = await getApplicationDocumentsDirectory();
        path = '${dir.path}/voice_temp.wav';
      }
      
      if (await _audioRecorder.hasPermission()) {
        final config = RecordConfig(encoder: kIsWeb ? AudioEncoder.aacLc : AudioEncoder.wav);
        await _audioRecorder.start(config, path: path ?? '');
        setState(() => _isRecording = true);
      }
    }
  }

  Future<void> _stopAndAnalyze() async {
    final path = await _audioRecorder.stop();
    setState(() => _isRecording = false);
    if (path == null) return;
    setState(() => _isLoading = true);

    try {
      var request = http.MultipartRequest('POST', Uri.parse('$baseUrl/analyze-voice'));
      if (kIsWeb) {
        var blob = await http.get(Uri.parse(path));
        request.files.add(http.MultipartFile.fromBytes('file', blob.bodyBytes, filename: 'voice.mp4'));
      } else {
        request.files.add(await http.MultipartFile.fromPath('file', path));
      }

      var res = await http.Response.fromStream(await request.send());
      if (res.statusCode == 200) {
        if (mounted) _showConfirmDialog(jsonDecode(utf8.decode(res.bodyBytes)));
      } else {
        if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text("인식 실패")));
      }
    } catch (e) {
      print(e);
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  void _showConfirmDialog(Map<String, dynamic> data) {
    TextEditingController titleController = TextEditingController(text: data['suggested_title']);
    String? parsedDate = data['parsed_date'];
    DateTime dateObj = parsedDate != null ? DateTime.parse(parsedDate) : DateTime.now(); // 없으면 오늘

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      builder: (context) {
        return StatefulBuilder( // 팝업 내부 상태 갱신을 위해 추가
          builder: (context, setModalState) {
            return Padding(
              padding: EdgeInsets.only(bottom: MediaQuery.of(context).viewInsets.bottom + 20, top: 20, left: 20, right: 20),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Text("저장 확인", style: TextStyle(fontWeight: FontWeight.bold, fontSize: 18)),
                  TextField(controller: titleController, decoration: const InputDecoration(labelText: "할 일")),
                  const SizedBox(height: 10),
                  Row(
                    children: [
                      const Icon(Icons.calendar_month),
                      TextButton(
                        onPressed: () async {
                           // 날짜 수동 변경
                           final picked = await showDatePicker(
                             context: context, initialDate: dateObj, firstDate: DateTime(2020), lastDate: DateTime(2030)
                           );
                           if(picked != null) {
                             final time = await showTimePicker(context: context, initialTime: TimeOfDay.fromDateTime(dateObj));
                             if(time != null) {
                               setModalState(() { // 팝업 화면 갱신
                                 dateObj = DateTime(picked.year, picked.month, picked.day, time.hour, time.minute);
                               });
                             }
                           }
                        },
                        child: Text(DateFormat('yyyy-MM-dd HH:mm').format(dateObj)),
                      )
                    ],
                  ),
                  ElevatedButton(
                    onPressed: () {
                      _saveTask(titleController.text, dateObj);
                      Navigator.pop(context);
                    },
                    child: const Text("저장"),
                  )
                ],
              ),
            );
          }
        );
      },
    );
  }

  Future<void> _saveTask(String title, DateTime date) async {
    try {
      await http.post(
        Uri.parse('$baseUrl/tasks'),
        headers: {"Content-Type": "application/json"},
        body: jsonEncode({
          "title": title,
          "due_date": date.toIso8601String(),
          "description": "음성 입력"
        }),
      );
      _fetchTasks();
      // 저장 후 해당 날짜로 이동
      setState(() => _selectedDay = date);
    } catch (e) { print(e); }
  }

  // --- 화면 구성 ---
  @override
  Widget build(BuildContext context) {
    // 선택된 날짜의 할 일만 가져오기
    final dailyTasks = _getTasksForDay(_selectedDay);

    return Scaffold(
      appBar: AppBar(title: const Text("Voice To-Do")),
      body: Column(
        children: [
          // 1. 달력
          TableCalendar(
            locale: 'ko_KR', // 한국어 달력
            firstDay: DateTime.utc(2020, 1, 1),
            lastDay: DateTime.utc(2030, 12, 31),
            focusedDay: _focusedDay,
            selectedDayPredicate: (day) => isSameDay(_selectedDay, day),
            onDaySelected: (selectedDay, focusedDay) {
              setState(() {
                _selectedDay = selectedDay;
                _focusedDay = focusedDay;
              });
            },
            calendarFormat: CalendarFormat.week, // 주간 보기
            headerStyle: const HeaderStyle(formatButtonVisible: false, titleCentered: true),
          ),
          const Divider(),
          // 2. 할 일 리스트
          Expanded(
            child: _isLoading 
              ? const Center(child: CircularProgressIndicator()) 
              : dailyTasks.isEmpty 
                ? const Center(child: Text("할 일이 없습니다."))
                : ListView.builder(
                    itemCount: dailyTasks.length,
                    itemBuilder: (context, index) {
                      final task = dailyTasks[index];
                      final date = DateTime.parse(task['due_date']);
                      
                      // 삭제를 위한 밀기(Swipe) 기능
                      return Dismissible(
                        key: Key(task['id'].toString()),
                        direction: DismissDirection.endToStart,
                        background: Container(color: Colors.red, alignment: Alignment.centerRight, padding: const EdgeInsets.only(right: 20), child: const Icon(Icons.delete, color: Colors.white)),
                        onDismissed: (direction) {
                          _deleteTask(task['id']);
                        },
                        child: ListTile(
                          onTap: () => _editTask(task), // 누르면 수정
                          leading: Checkbox(
                            value: task['is_completed'] ?? false,
                            onChanged: (v) => _toggleTaskStatus(task['id'], task['is_completed']),
                          ),
                          title: Text(
                            task['title'],
                            style: TextStyle(
                              decoration: (task['is_completed'] ?? false) ? TextDecoration.lineThrough : null,
                              color: (task['is_completed'] ?? false) ? Colors.grey : null
                            ),
                          ),
                          subtitle: Text(DateFormat('a h:mm', 'ko_KR').format(date)),
                        ),
                      );
                    },
                  ),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton(
        backgroundColor: _isRecording ? Colors.red : Colors.blue,
        onPressed: _isRecording ? _stopAndAnalyze : _startRecording,
        child: Icon(_isRecording ? Icons.stop : Icons.mic),
      ),
      floatingActionButtonLocation: FloatingActionButtonLocation.centerFloat,
    );
  }
}
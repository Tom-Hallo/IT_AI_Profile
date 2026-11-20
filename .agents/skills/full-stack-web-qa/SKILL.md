---
name: full-stack-web-qa
description: "Audit and fix web functionality through source review and real browser interaction. Use for end-to-end QA, interaction bugs, and multi-round regression testing."
---

# Full-stack Web QA

## Chuẩn bị

- Đọc cách chạy dự án, test, lint và build từ README, package scripts và CI.
- Lập danh sách theo màn hình, thao tác, kết quả mong đợi và lớp code liên quan.
- Ưu tiên các chức năng ảnh hưởng nhiều màn hình hoặc có dữ liệu và trạng thái dùng chung.

## Kiểm tra và sửa từng lỗi

1. Tái hiện lỗi trên trình duyệt khi lỗi xuất phát từ một thao tác người dùng.
2. Ghi rõ điều kiện ban đầu, bước thao tác, kết quả thực tế và kết quả mong đợi.
3. Theo dấu từ sự kiện UI đến request, backend và dữ liệu trả về. Với tác vụ chạy nền, kiểm tra cả lúc chờ, lúc hoàn tất và lúc thất bại.
4. Sửa nguyên nhân gốc. Thêm ca test hồi quy khi test hiện có chưa thể bắt lại lỗi.
5. Lặp lại đúng thao tác gây lỗi trên UI và kiểm tra thêm các luồng dùng chung component, API hoặc trạng thái.
6. Lưu bằng chứng phù hợp như kết quả test, trạng thái UI, ảnh hoặc thông tin request đã loại bỏ dữ liệu nhạy cảm.

## Các vòng kiểm tra

| Vòng | Trọng tâm |
| --- | --- |
| 1 | Đối chiếu source với ứng dụng đang chạy. Xác minh các luồng chính từ đầu đến cuối. |
| 2 | Kiểm tra nút, tab, form, modal, bàn phím, focus, cuộn và viewport mobile. |
| 3 | Kiểm tra quyền, dữ liệu rỗng, lỗi API, phiên hết hạn và khả năng thử lại. |
| 4 | Kiểm tra bấm nhanh, request chậm, đổi tab khi đang tải, refresh và back/forward. |
| 5 | Chạy hồi quy trên bản sau sửa, kiểm tra lại chức năng liên quan và chạy các lệnh test, lint, build phù hợp với repo. |

Mỗi vòng ghi lại ca đã chạy, kết quả và thay đổi phát sinh. Chạy thêm vòng nếu phát hiện lỗi mới. Sau lần sửa cuối, chạy lại bộ hồi quy trên bản code cuối.

## Trạng thái kết quả

- PASS — Đã xác nhận kết quả mong đợi và có bằng chứng.
- FAIL — Đã tái hiện kết quả sai. Ghi nguyên nhân hoặc dấu hiệu đang điều tra.
- BLOCKED — Ghi điều kiện còn thiếu và phần có thể kiểm tra được.
- Nếu dùng mock, ghi rõ bằng chứng đó xác nhận phần nào của luồng và phần nào cần dịch vụ thật. 
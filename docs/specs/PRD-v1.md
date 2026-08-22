# PRD — Vivu RAG Chatbot

> **Version:** `v1`

> **Owner:** `DuyenNTB`

> **Last Updated:** `30/07/2026`

## 1. Product Overview

- **Product Name:** Vivu
- **Automotive Brand:** VinFast
- **Market:** Việt Nam
- **Supported Languages:** Tiếng Việt
- **Deployment Channels:** Website
- **Target MVP Launch Date:** 21/08
- **Product Owner:** `DuyenNTB`

### Product Summary

Vivu là RAG Chatbot hỗ trợ khách hàng tìm hiểu và sử dụng xe VinFast. Sản phẩm giúp người dùng tra cứu thông số kỹ thuật, giá, khuyến mãi, bảo hành, sạc pin, hướng dẫn sử dụng và so sánh các mẫu xe dựa trên nguồn dữ liệu chính thức.

Chatbot phục vụ hai nhóm người dùng chính: khách hàng đang tìm hiểu mua xe và khách hàng đã sở hữu xe VinFast.

## 2. Problem Statement

Khách hàng VinFast cần tìm kiếm và đối chiếu nhiều loại thông tin như thông số kỹ thuật, giá, khuyến mãi, bảo hành, sạc pin và so sánh xe. Tuy nhiên, thông tin nằm rải rác ở nhiều nguồn và có thể thay đổi theo thời gian, thị trường, mẫu xe hoặc phiên bản. Điều này khiến khách hàng khó tìm được câu trả lời nhanh, chính xác và đủ tin cậy để đưa ra quyết định.

### Common Problems

1. Thông tin nằm rải rác trên nhiều website, tài liệu và kênh hỗ trợ.
2. Người dùng mất nhiều thời gian để tìm đúng thông tin cần thiết.
3. Thông tin có thể cũ, mâu thuẫn hoặc không đúng với trường hợp cụ thể.
4. Câu trả lời thiếu nguồn kiểm chứng làm giảm mức độ tin tưởng.

### Prospective Customer Problems

1. Khó lựa chọn mẫu xe và phiên bản phù hợp với nhu cầu thực tế.
2. Khó so sánh xe do thông tin nhiều, phức tạp và thiếu nhất quán.
3. Không hiểu rõ các thông số kỹ thuật và ảnh hưởng của chúng đến trải nghiệm sử dụng.
4. Khó xác định giá, ưu đãi và chính sách đang còn hiệu lực.
5. Thiếu thông tin rõ ràng về sạc pin, phạm vi di chuyển và chi phí sở hữu.

### Existing Customer Problems

1. Khó tìm nhanh hướng dẫn phù hợp trong User Manual.
2. Không biết cách sử dụng hoặc cấu hình một số tính năng của xe.
3. Khó xác định thông tin bảo hành.

## 3. Business Goals & User Goals

### Business Goal

Xây dựng một kênh tư vấn tự phục vụ đáng tin cậy, giúp khách hàng tìm được thông tin chính xác và phù hợp nhanh hơn trong suốt quá trình tìm mua và sử dụng xe VinFast.

### Business Outcomes

1. **Tăng khả năng tự phục vụ:** Tăng tỷ lệ khách hàng tự tìm được câu trả lời mà không cần liên hệ nhân viên.
2. **Giảm thời gian tìm kiếm thông tin:** Giúp khách hàng tiếp cận đúng thông tin từ nguồn chính thức nhanh hơn.
3. **Hỗ trợ quyết định mua xe:** Giúp khách hàng hiểu, lựa chọn và so sánh các mẫu xe phù hợp với nhu cầu.
4. **Cải thiện trải nghiệm sau mua:** Giúp chủ xe nhanh chóng tìm được hướng dẫn sử dụng và thông tin bảo hành.
5. **Giảm tải cho đội ngũ hỗ trợ:** Giảm số lượng câu hỏi phổ biến cần Sales hoặc Customer Support xử lý thủ công.
6. **Duy trì độ tin cậy khi mở rộng:** Đảm bảo chất lượng trả lời và tốc độ phản hồi ổn định khi số lượng người dùng hoặc dữ liệu tăng.

### User Goals

- Tìm được thông tin phù hợp từ nguồn chính thức.
- Hiểu sự khác nhau giữa các mẫu xe và phiên bản.
- Nhận gợi ý xe phù hợp với nhu cầu và ngân sách.
- Tìm được hướng dẫn sử dụng và thông tin bảo hành phù hợp với xe đang sở hữu.
- Biết khi nào chatbot không thể hỗ trợ và cách liên hệ hotline chính thức.

### Non-goals

- Thay thế hoàn toàn Sales, Customer Support hoặc kỹ thuật viên.
- Thực hiện giao dịch, chẩn đoán kỹ thuật hoặc đưa ra cam kết thay mặt VinFast.

## 4. User Segments

### Primary User Segment 1 — Prospective Customers

**Description:** Người đang tìm hiểu, cân nhắc hoặc có kế hoạch mua xe VinFast nhưng chưa xác định được mẫu xe hoặc phiên bản phù hợp.

**Characteristics:**

- Có mức độ hiểu biết về xe điện và sản phẩm VinFast khác nhau.
- Quan tâm đến giá, ưu đãi, thông số, phạm vi di chuyển và sạc pin.
- Thường so sánh nhiều mẫu xe trước khi quyết định.
- Muốn nhận thông tin nhanh trước khi liên hệ Sales.
- Muốn nhận thông tin về xe phù hợp với nhu cầu cá nhân.

**Primary Needs:**

- Tìm mẫu xe phù hợp với nhu cầu và ngân sách.
- Hiểu sự khác nhau giữa các mẫu xe và phiên bản.
- Tra cứu giá, ưu đãi và chính sách đang còn hiệu lực.
- Tìm hiểu chi phí sử dụng, sạc pin và bảo hành.
- Được hướng dẫn cách đăng ký lái thử hoặc liên hệ Sales khi có nhu cầu.

**Expected Outcome:** Người dùng hiểu rõ lựa chọn của mình, tìm được mẫu xe phù hợp và biết bước tiếp theo để tiếp tục quá trình mua xe.

### Primary User Segment 2 — Existing Customers

**Description:** Khách hàng đang sở hữu hoặc sử dụng xe VinFast và cần hỗ trợ trong quá trình sử dụng xe.

**Characteristics:**

- Đã sở hữu một mẫu xe và phiên bản cụ thể.
- Cần câu trả lời đúng với chiếc xe đang sử dụng.
- Thường tìm hỗ trợ khi cần sử dụng tính năng hoặc gặp vấn đề.
- Có thể cần phản hồi nhanh trong những tình huống khẩn cấp.

**Primary Needs:**

- Tìm hướng dẫn sử dụng tính năng của xe.
- Tra cứu chính sách và thời hạn bảo hành.
- Tìm hiểu lịch bảo dưỡng và địa điểm dịch vụ.
- Được hướng dẫn về sạc pin và tối ưu phạm vi di chuyển.
- Hiểu ý nghĩa của các cảnh báo hoặc vấn đề thường gặp.
- Được cung cấp hotline phù hợp khi cần hỗ trợ trực tiếp.

**Expected Outcome:** Chủ xe nhanh chóng tìm được hướng dẫn phù hợp, biết cách xử lý bước đầu và được cung cấp đúng kênh hỗ trợ khi chatbot không thể giải quyết.

## 5. MVP Scope

MVP tập trung giúp hai nhóm người dùng tìm được thông tin chính xác, dễ hiểu và có thể kiểm chứng từ nguồn dữ liệu chính thức của VinFast.

### Must-have Features

1. **Question Answering**
   - Trả lời câu hỏi về thông số, tính năng, giá, khuyến mãi, bảo hành, bảo dưỡng, sạc pin và hướng dẫn sử dụng.
   - Câu trả lời phải dựa trên approved Data Sources.

2. **Semantic Search**
   - Tìm nội dung theo ý nghĩa câu hỏi thay vì chỉ dựa trên từ khóa.
   - Trả về đúng thông tin theo mẫu xe, phiên bản và chủ đề.

3. **Context Clarification**
   - Hỏi lại khi thiếu thông tin quan trọng như mẫu xe, phiên bản hoặc nhu cầu sử dụng.
   - Không tự giả định thông tin chưa được người dùng cung cấp.

4. **Context-aware Conversation**
   - Hiểu câu hỏi tiếp nối trong cùng một cuộc hội thoại.
   - Giữ đúng mẫu xe hoặc chủ đề đang được trao đổi.

5. **Vehicle Comparison**
   - So sánh các mẫu xe hoặc phiên bản theo tiêu chí người dùng quan tâm.
   - Chỉ sử dụng thông tin có trong nguồn chính thức.

6. **Vehicle Recommendation**
   - Gợi ý mẫu xe dựa trên nhu cầu, ngân sách và thói quen di chuyển.
   - Giải thích lý do đề xuất và không quyết định thay người dùng.

7. **Source Citation**
   - Cung cấp nguồn cho các thông tin có thể kiểm chứng.
   - Không sử dụng nguồn đã hết hiệu lực hoặc chưa được phê duyệt.

8. **Out-of-scope Handling**
   - Nhận biết câu hỏi nằm ngoài phạm vi hỗ trợ.
   - Không suy đoán khi thiếu dữ liệu hoặc không tìm thấy nguồn phù hợp.

9. **Support Hotline**
   - Hiển thị số hotline chính thức khi chatbot không thể trả lời hoặc người dùng cần hỗ trợ trực tiếp.
   - Hiển thị số điện thoại dưới dạng có thể nhấn để gọi.
   - Chỉ sử dụng số hotline đã được VinFast xác nhận và còn hiệu lực.
   - Với vấn đề liên quan đến an toàn, hướng dẫn người dùng ngừng thao tác không an toàn và gọi hotline ngay.

10. **Vietnamese Web Experience**
    - Hoạt động trên Website và hỗ trợ tiếng Việt.
    - Câu trả lời ngắn gọn, dễ hiểu và phù hợp với trải nghiệm hội thoại.

### MVP Prioritization Rule

Một capability chỉ thuộc MVP khi:

- Tạo giá trị trực tiếp cho một trong hai Primary User Segments.
- Có approved Data Source đủ tin cậy.
- Có Acceptance Criteria và cách đo lường rõ ràng.

## 6. Out of Scope

1. Thực hiện đặt cọc, thanh toán hoặc mua xe trực tiếp.
2. Phê duyệt khoản vay hoặc đưa ra cam kết về tài chính.
3. Xác nhận giá cuối cùng hoặc tình trạng xe tại từng đại lý theo thời gian thực.
4. Tự động đặt lịch lái thử, bảo dưỡng hoặc sửa chữa; chatbot chỉ hướng dẫn người dùng đến kênh phù hợp.
5. Truy cập tài khoản, lịch sử dịch vụ, VIN hoặc Personal Customer Data.
6. Chẩn đoán lỗi kỹ thuật hoặc đưa ra hướng dẫn sửa chữa có thể ảnh hưởng đến an toàn.
7. Thay thế quyết định của Sales, Customer Support hoặc kỹ thuật viên.
8. Trả lời bằng nguồn Internet hoặc nguồn bên ngoài chưa được VinFast phê duyệt.
9. Hỗ trợ Voice, Image hoặc file do người dùng tải lên.
10. Hỗ trợ ngôn ngữ khác ngoài tiếng Việt.
11. Ghi nhớ thông tin người dùng giữa các phiên hội thoại.
12. Đưa ra cam kết pháp lý hoặc cam kết chính thức thay mặt VinFast.

## 7. Key Use Cases & User Journeys

### UC-01 — Product Information

- **Priority:** `[MUST]`
- **User Story:** Là người đang tìm hiểu mua xe, tôi muốn tra cứu thông số, tính năng, giá và chính sách để hiểu rõ một mẫu xe hoặc phiên bản.

### UC-02 — Vehicle Comparison

- **Priority:** `[MUST]`
- **User Story:** Là người đang cân nhắc mua xe, tôi muốn so sánh các mẫu xe hoặc phiên bản theo tiêu chí mình quan tâm để lựa chọn dễ dàng hơn.

### UC-03 — Vehicle Recommendation

- **Priority:** `[MUST]`
- **User Story:** Là người chưa xác định được mẫu xe phù hợp, tôi muốn nhận gợi ý dựa trên nhu cầu, ngân sách và thói quen di chuyển để thu hẹp lựa chọn.
- **Expected Behavior:** Chatbot giải thích lý do đề xuất thay vì chỉ đưa ra tên xe.

### UC-04 — Pricing & Promotion

- **Priority:** `[MUST]`
- **User Story:** Là người đang tìm mua xe, tôi muốn tra cứu giá, ưu đãi và chính sách còn hiệu lực để ước tính chi phí và đưa ra quyết định.

### UC-05 — Charging & Ownership Information

- **Priority:** `[MUST]`
- **User Story:** Là người đang cân nhắc xe điện, tôi muốn tìm hiểu về sạc pin, phạm vi di chuyển, chi phí sử dụng và bảo hành để đánh giá khả năng đáp ứng nhu cầu.

### UC-06 — Sales Support

- **Priority:** `[NICE-TO-HAVE]`
- **User Story:** Là người đã tìm được mẫu xe phù hợp, tôi muốn biết cách tìm showroom, đăng ký lái thử hoặc liên hệ Sales để tiếp tục quá trình mua xe.

### Example Questions

1. “VF 6 có những phiên bản nào và khác nhau ở điểm gì?”
2. “So sánh VF 6 và VF 7 theo nhu cầu đi lại trong thành phố.”
3. “Gia đình bốn người, ngân sách khoảng 800 triệu thì nên chọn xe nào?”
4. “Giá và ưu đãi hiện tại của VF 8 là bao nhiêu?”
5. “Xe có thể đi được bao xa sau một lần sạc?”
6. “Tôi muốn đăng ký lái thử thì cần làm gì?”
7. “Làm thế nào để cài đặt giới hạn sạc pin trên xe?”
8. “Xe của tôi được bảo hành trong bao lâu?”
9. “Khi nào tôi cần đưa xe đi bảo dưỡng?”

### Use Cases Still Needed

Các Use Cases chi tiết cho Existing Customers ngoài những Example Questions hiện vẫn cần được bổ sung.

## 8. Functional Requirements & Acceptance Criteria

### FR-01 — Grounded Question Answering

- **Priority:** `[MUST]`
- **Requirement:** System phải trả lời các chủ đề thuộc MVP Scope dựa trên approved Data Sources.

**Acceptance Criteria:**

- Khi có đủ dữ liệu phù hợp, câu trả lời chỉ chứa thông tin được hỗ trợ bởi nguồn truy xuất.
- Khi không có đủ dữ liệu, System không suy đoán và thông báo không thể xác nhận.
- Câu trả lời phải đúng với mẫu xe, phiên bản và chủ đề đã được xác định.

### FR-02 — Semantic Search

- **Priority:** `[MUST]`
- **Requirement:** System phải tìm được nội dung liên quan theo ý nghĩa câu hỏi, không chỉ dựa trên từ khóa trùng khớp.

**Acceptance Criteria:**

- Kết quả ưu tiên nội dung đúng với ý định, mẫu xe, phiên bản và chủ đề của câu hỏi.
- Câu hỏi dùng cách diễn đạt phổ thông vẫn có thể tìm được nội dung liên quan khi dữ liệu tồn tại.

### FR-03 — Context Clarification

- **Priority:** `[MUST]`
- **Requirement:** System phải hỏi lại khi thiếu thông tin cần thiết để trả lời chính xác.

**Acceptance Criteria:**

- System chỉ hỏi thông tin cần thiết như mẫu xe, phiên bản, thời điểm hoặc nhu cầu sử dụng.
- System không tự gán thông tin người dùng chưa cung cấp.

### FR-04 — Context-aware Conversation

- **Priority:** `[MUST]`
- **Requirement:** System phải hiểu câu hỏi tiếp nối trong cùng một phiên hội thoại.

**Acceptance Criteria:**

- System duy trì đúng mẫu xe, phiên bản và chủ đề đã được xác định.
- System không ghi nhớ thông tin người dùng sau khi phiên hội thoại kết thúc.

### FR-05 — Vehicle Comparison

- **Priority:** `[MUST]`
- **Requirement:** System phải so sánh các mẫu xe hoặc phiên bản theo tiêu chí người dùng yêu cầu.

**Acceptance Criteria:**

- Chỉ so sánh các tiêu chí có dữ liệu chính thức.
- Nêu rõ mẫu xe và phiên bản được so sánh.
- Không tự điền thông tin còn thiếu hoặc trộn dữ liệu giữa các phiên bản.

### FR-06 — Vehicle Recommendation

- **Priority:** `[MUST]`
- **Requirement:** System phải gợi ý mẫu xe dựa trên nhu cầu, ngân sách và thói quen di chuyển do người dùng cung cấp.

**Acceptance Criteria:**

- System hỏi lại nếu chưa có đủ thông tin để đưa ra gợi ý.
- Mỗi gợi ý phải có lý do dựa trên tiêu chí người dùng cung cấp.
- System trình bày gợi ý để tham khảo, không khẳng định thay cho quyết định của người dùng.

### FR-07 — Source Citation

- **Priority:** `[MUST]`
- **Requirement:** System phải cung cấp Source Citation cho các thông tin có thể kiểm chứng.

**Acceptance Criteria:**

- Citation liên kết đúng với nguồn được sử dụng.
- Citation liên quan trực tiếp đến nội dung trả lời.
- Nguồn hết hiệu lực hoặc chưa được phê duyệt không được hiển thị như nguồn hợp lệ.

### FR-08 — Out-of-scope Handling

- **Priority:** `[MUST]`
- **Requirement:** System phải nhận biết và xử lý câu hỏi ngoài phạm vi hoặc không có đủ dữ liệu.

**Acceptance Criteria:**

- System thông báo rõ giới hạn và không tạo câu trả lời bằng suy đoán.
- System yêu cầu làm rõ nếu có thể xử lý sau khi bổ sung thông tin.
- System hiển thị hotline khi người dùng cần hỗ trợ trực tiếp.

### FR-09 — Support Hotline

- **Priority:** `[MUST]`
- **Requirement:** System phải hiển thị hotline chính thức trong các trường hợp cần hỗ trợ trực tiếp.

**Acceptance Criteria:**

- Hotline được lấy từ nguồn chính thức còn hiệu lực.
- Số điện thoại có thể nhấn để gọi trên thiết bị hỗ trợ.
- Với vấn đề liên quan đến an toàn, System hướng dẫn người dùng ngừng thao tác không an toàn và gọi hotline ngay.

### FR-10 — Vietnamese Web Experience

- **Priority:** `[MUST]`
- **Requirement:** Chatbot phải hoạt động trên Website và trả lời bằng tiếng Việt.

**Acceptance Criteria:**

- Câu trả lời sử dụng tiếng Việt, trừ tên riêng và thuật ngữ cần thiết.
- Nội dung ngắn gọn, dễ hiểu và phù hợp với trải nghiệm hội thoại.

## 9. AI Requirements

Phần này xác định AI phải làm được gì và các nguyên tắc phải tuân thủ khi trả lời người dùng.

### Capabilities

1. **Question Understanding**
   - Hiểu câu hỏi bằng tiếng Việt, kể cả khi người dùng sử dụng cách nói tự nhiên, kém trang trọng hoặc không dùng đúng tên kỹ thuật.
   - Xác định nhu cầu chính như tìm hiểu sản phẩm, so sánh xe, tư vấn lựa chọn, bảo hành hoặc hướng dẫn sử dụng.

2. **Grounded Question Answering**
   - Trả lời dựa trên approved Data Sources của VinFast.
   - Mọi thông tin về giá, thông số, khuyến mãi, bảo hành và hướng dẫn sử dụng phải có dữ liệu hỗ trợ.

3. **Semantic Search**
   - Tìm nội dung liên quan dựa trên ý nghĩa câu hỏi, không chỉ dựa trên từ khóa.
   - Ưu tiên kết quả đúng với mẫu xe, phiên bản, thị trường và chủ đề người dùng đang hỏi.

4. **Context Clarification**
   - Hỏi lại khi thiếu thông tin cần thiết như mẫu xe, phiên bản, thời điểm hoặc nhu cầu sử dụng.
   - Không tự chọn mẫu xe hoặc phiên bản thay cho người dùng.

5. **Context-aware Conversation**
   - Hiểu câu hỏi tiếp nối trong cùng một phiên hội thoại.
   - Duy trì đúng mẫu xe, phiên bản và chủ đề đã được xác định.
   - Không ghi nhớ thông tin người dùng sau khi phiên hội thoại kết thúc.

6. **Vehicle Comparison & Recommendation**
   - So sánh xe theo các tiêu chí người dùng yêu cầu.
   - Gợi ý mẫu xe dựa trên nhu cầu và ngân sách được cung cấp.
   - Giải thích lý do đề xuất và cho biết thông tin nào còn thiếu.

7. **Source Citation**
   - Cung cấp nguồn chính thức cho các thông tin có thể kiểm chứng.
   - Citation phải liên quan trực tiếp đến nội dung trả lời.

8. **Out-of-scope Detection**
   - Nhận biết câu hỏi nằm ngoài phạm vi hoặc không có đủ dữ liệu.
   - Thông báo rõ giới hạn và hướng dẫn người dùng gọi hotline khi cần hỗ trợ trực tiếp.

### Guardrails

- Không tự bịa, suy đoán hoặc trình bày thông tin chưa được kiểm chứng như sự thật.
- Chỉ sử dụng approved Data Sources của VinFast.
- Không sử dụng kiến thức từ Internet hoặc nguồn bên ngoài chưa được phê duyệt.
- Không trộn thông tin giữa các mẫu xe, phiên bản hoặc thị trường khác nhau.
- Ưu tiên nguồn chính thức mới nhất còn hiệu lực.
- Khi dữ liệu thiếu hoặc mâu thuẫn, phải thông báo không thể xác nhận thay vì tự lựa chọn câu trả lời.
- Yêu cầu người dùng làm rõ khi câu hỏi chưa đủ thông tin.
- Không yêu cầu hoặc tiết lộ Personal Data và Sensitive Data.
- Không chẩn đoán lỗi kỹ thuật hoặc hướng dẫn sửa chữa có thể gây mất an toàn.
- Không đưa ra cam kết về giá, tài chính, pháp lý hoặc chính sách thay mặt VinFast.
- Không khẳng định một mẫu xe chắc chắn phù hợp; chỉ đưa ra gợi ý và lý do tham khảo.

### Refusal Rules

AI phải từ chối hoặc giới hạn câu trả lời khi:

1. Không tìm thấy thông tin phù hợp trong approved Data Sources.
2. Các nguồn dữ liệu mâu thuẫn và không thể xác định nguồn còn hiệu lực.
3. Câu hỏi nằm ngoài các Use Cases được hỗ trợ.
4. Người dùng yêu cầu thông tin từ nguồn bên ngoài chưa được phê duyệt.
5. Người dùng yêu cầu truy cập tài khoản, VIN, lịch sử dịch vụ hoặc Personal Customer Data.
6. Người dùng yêu cầu chẩn đoán hoặc hướng dẫn xử lý vấn đề có thể ảnh hưởng đến an toàn.
7. Người dùng yêu cầu AI đưa ra cam kết về giá, tài chính hoặc pháp lý.

Khi từ chối, AI phải:

- Nói rõ không thể xác nhận hoặc không có đủ thông tin.
- Không tạo câu trả lời thay thế bằng suy đoán.
- Đề nghị người dùng bổ sung thông tin nếu có thể giải quyết bằng clarification.
- Hiển thị hotline chính thức nếu cần hỗ trợ trực tiếp.

### Support Hotline Conditions

AI phải hiển thị hotline chính thức khi:

1. Người dùng chủ động yêu cầu liên hệ nhân viên.
2. Không tìm thấy câu trả lời sau khi đã yêu cầu làm rõ.
3. Vấn đề liên quan đến cảnh báo, sự cố hoặc an toàn của xe.
4. Người dùng cần hỗ trợ liên quan đến tài khoản hoặc thông tin cá nhân.
5. Người dùng cần xác nhận giá, ưu đãi hoặc chính sách cho trường hợp cụ thể.
6. Câu hỏi cần Sales, Customer Support hoặc Service Center xử lý.

Hotline phải:

- Được lấy từ nguồn chính thức còn hiệu lực.
- Phù hợp với loại hỗ trợ người dùng cần.
- Hiển thị dưới dạng có thể nhấn để gọi trên thiết bị hỗ trợ.
- Kèm mô tả ngắn về lý do người dùng nên gọi.

### Response Rules

- **Default Language:** Tiếng Việt.
- **Tone of Voice:** Thân thiện, chuyên nghiệp và dễ hiểu.
- **Expected Response Length:** Trả lời ngắn gọn trước; chỉ giải thích chi tiết khi cần hoặc khi người dùng yêu cầu.
- **Source Citation Required:** Yes, đối với các thông tin có thể kiểm chứng.
- **External Knowledge Allowed:** No.
- Trả lời trực tiếp vào câu hỏi, tránh nội dung không liên quan.
- Ưu tiên cách diễn đạt phổ thông thay vì thuật ngữ kỹ thuật.
- Nêu rõ mẫu xe hoặc phiên bản đang được đề cập khi có nguy cơ nhầm lẫn.
- Nêu thời điểm áp dụng đối với giá, khuyến mãi và chính sách.
- Phân biệt rõ thông tin chính thức với gợi ý mang tính tham khảo.
- Không suy đoán khi không có đủ dữ liệu.

## 10. Response, Refusal & Human Handoff Rules

**Purpose:** Đảm bảo câu trả lời nhất quán, an toàn và trung thực.

### Response Rules

- [ ] Trả lời trực tiếp, ngắn gọn và đúng ngôn ngữ của User.
- [ ] Chỉ sử dụng approved retrieved evidence cho factual claims.
- [ ] Phân biệt rõ fact, limitation và required next step.
- [ ] Cung cấp Source Citation khi có factual claim.

### Refusal Rules

System phải từ chối hoặc giới hạn trả lời khi:

- Không có sufficient evidence.
- Request nằm ngoài Scope.
- Request yêu cầu cam kết pháp lý, tài chính hoặc an toàn không được hỗ trợ.
- Request yêu cầu truy cập dữ liệu trái quyền hạn.
- Retrieved content mâu thuẫn và không thể xác định authoritative source.

### Human Handoff Conditions

- User yêu cầu gặp Human Agent.
- User thể hiện complaint hoặc escalation intent.
- Request liên quan đến safety-critical issue.
- Cần truy cập Customer-specific Data ngoài quyền của chatbot.
- Clarification không giải quyết được ambiguity.
- System confidence thấp hơn approved threshold: `[TBD]`.
# Vietnamese strings recommended for native review

Project 873 refreshed the interface against 0.1.12 on 2026-11-26. Open the named control in Vietnamese and compare the current wording with the alternative in context. Start with the five translations marked as drafts.

## 1. Account

- **English** We keep the words you look up, save and mark, with their times, on our server. This lets saved words and progress follow you to another PC and shows us how people learn. You can delete this data for every language from our server, and choose whether to also delete it from this PC.
- **Vietnamese** Chúng tôi lưu trên máy chủ các từ bạn tra, lưu hoặc đánh dấu, kèm thời điểm. Nhờ vậy, từ đã lưu và tiến độ học có trên máy tính khác, và chúng tôi hiểu cách mọi người học. Bạn có thể xóa dữ liệu này của mọi ngôn ngữ khỏi máy chủ và chọn có xóa cả trên máy này hay không.
- **Alternative** Chúng tôi lưu trên máy chủ những từ bạn đã tra, lưu hoặc đánh dấu cùng thời điểm tương ứng. Nhờ vậy, bạn có thể tiếp tục học trên máy khác và chúng tôi hiểu cách người dùng học. Bạn có thể xóa dữ liệu của mọi ngôn ngữ khỏi máy chủ và chọn xóa cả trên máy này.
- **In context** Check that thời điểm reads as the timestamp of each action and that the scope of deletion is unmistakable. [account_page.py](../../src/polyglotic_desktop/ui_next/account_page.py)

## 2. CallNotice

- **English** In some places everyone on a call has to agree before it's captioned. Tell the people you're talking with.
- **Vietnamese** Ở một số nơi, mọi người trong cuộc gọi phải đồng ý trước khi bật phụ đề. Hãy báo cho những người đang nói chuyện với bạn.
- **Alternative** Ở một số nơi, chỉ được bật phụ đề cuộc gọi khi mọi người đồng ý. Hãy báo cho những người cùng gọi.
- **In context** Check the register in the one-time notice before captioning a call. [main.py](../../src/polyglotic_desktop/main.py)

## 3. CaptionSetUp

- **English** Shown as "You". Your mic is sent for your captions only while this is on.
- **Vietnamese** Phụ đề lời bạn nói mang nhãn “Bạn”. Âm thanh micrô chỉ được gửi để tạo phụ đề khi bật mục này.
- **Alternative** Lời bạn nói hiện với nhãn “Bạn”. Khi bật, ứng dụng gửi âm thanh từ micrô để tạo phụ đề cho bạn.
- **In context** Check clarity beside the microphone switch. [caption_set_up.py](../../src/polyglotic_desktop/ui_next/caption_set_up.py)

## 4. CaptionWindow

- **English** Quiet view
- **Vietnamese** Xem yên tĩnh
- **Alternative** Dịu mắt
- **In context** Check whether the existing label suggests muted audio to a reader who sees it without the tooltip. [caption_window.py](../../src/polyglotic_desktop/ui_next/caption_window.py)

## 5. CaptionWindow

- **English** Line up the parts, in every window: each part of what was said starts where its translation does, so a word's translation is under it
- **Vietnamese** Căn thẳng các phần ở mọi cửa sổ: căn đầu từng đoạn lời nói với đầu đoạn dịch để từ và bản dịch nằm trên dưới nhau
- **Alternative** Căn các đoạn ở mọi cửa sổ để từ và bản dịch nằm thẳng hàng theo chiều dọc.
- **In context** Check whether the explanation should emphasize paired segments or individual words. [caption_window.py](../../src/polyglotic_desktop/ui_next/caption_window.py)

## 6. CaptionWindow

- **English** Captions singing in music players whose spoken language is Detect. Their sound is sent even without speech, a few seconds at a time. Off: only speech is sent
- **Vietnamese** Tạo phụ đề tiếng hát trong trình phát nhạc đặt ngôn ngữ nói là Tự nhận. Âm thanh được gửi theo từng đoạn vài giây, kể cả khi không có lời nói. Khi tắt, chỉ lời nói được gửi
- **Alternative** Tạo phụ đề tiếng hát cho trình phát nhạc đang dùng Tự nhận. Khi bật, ứng dụng gửi âm thanh từng đoạn vài giây, kể cả lúc không có lời nói. Khi tắt, ứng dụng chỉ gửi lời nói.
- **In context** Check that the scope of the Detect condition and the audio-sharing distinction are clear. [caption_window.py](../../src/polyglotic_desktop/ui_next/caption_window.py)

## 7. CaptionWindow

- **English** Only words the speech model is sure of: later, but they stay put
- **Vietnamese** Chỉ hiện những từ mô hình đã nhận dạng chắc chắn. Chữ hiện muộn hơn và giữ nguyên
- **Alternative** Chỉ hiện từ mà hệ thống nhận dạng đủ chắc chắn. Chữ hiện chậm hơn nhưng không đổi.
- **In context** Check how technical a timing menu should sound. [timing_popover.py](../../src/polyglotic_desktop/ui_next/timing_popover.py)

## 8. Home

- **English** Also caption everything else
- **Vietnamese** Tạo phụ đề cả âm thanh khác
- **Alternative** Tạo phụ đề cho cả âm thanh còn lại
- **In context** Check that the Home switch means adding the remaining audio in a separate window. [home.py](../../src/polyglotic_desktop/ui_next/home.py)

## 9. Lab

- **English** Line by line: a line of what was said, then the line of its translation, both cut where their words match. A long clause that can't be cut wraps.
- **Vietnamese** Từng dòng một: sau mỗi dòng lời nói là dòng dịch. Ngắt hai dòng ở chỗ các từ tương ứng; mệnh đề dài không ngắt được sẽ tự xuống dòng.
- **Alternative** Từng dòng một: xen mỗi dòng gốc với dòng dịch. Ngắt ở những từ tương ứng; mệnh đề quá dài sẽ xuống dòng.
- **In context** Check whether dòng lời nói is easier to understand than dòng gốc in the Lab. [lab_panel.py](../../src/polyglotic_desktop/ui_next/lab_panel.py)

## 10. Learning

- **English** Link words after
- **Vietnamese draft** Liên kết từ sau ngưỡng
- **Alternative** Chỉ liên kết từ sau hạng này
- **In context** Check that a learner understands this as a frequency rank, not a frequency count. [learning_page.py](../../src/polyglotic_desktop/ui_next/learning_page.py)

## 11. Learning

- **English** Highlights this many words beyond your level. Rarer words are left alone; hover or click one to look it up.
- **Vietnamese** Làm nổi bật số từ này trong nhóm vượt trình độ. Từ hiếm hơn vẫn có thể tra bằng cách trỏ hoặc bấm vào.
- **Alternative** Làm nổi bật số từ này trong nhóm vượt trình độ. Trỏ hoặc bấm để tra các từ hiếm hơn.
- **In context** Check that the cap and the continued availability of lookup both read naturally. [learning_page.py](../../src/polyglotic_desktop/ui_next/learning_page.py)

## 12. Panels

- **English** The characters Mandarin captions are written in, with Detect too. Lookups, transcripts, copies and Anki use the same. Translations into Chinese keep the script you translate into.
- **Vietnamese draft** Chọn chữ giản thể hay phồn thể cho phụ đề tiếng Phổ thông, kể cả khi dùng Tự nhận. Tra từ, bản ghi, nội dung sao chép và Anki dùng cùng hệ chữ. Bản dịch tiếng Trung giữ hệ chữ bạn chọn khi dịch.
- **Alternative** Chọn chữ giản thể hoặc phồn thể cho lời nói tiếng Phổ thông, kể cả khi dùng Tự nhận. Tra từ, bản ghi, sao chép và Anki dùng cùng hệ chữ. Khi dịch sang tiếng Trung, dùng hệ chữ của ngôn ngữ đích.
- **In context** Check the distinction between the script for spoken Mandarin and the script selected as a translation target. [panels.py](../../src/polyglotic_desktop/ui_next/panels.py)

## 13. Panels

- **English** Words in what was said and its translation that mean the same. On hover: point at a word. Underline: colours show word class. Arrows: curves join them. A caption window's preset menu turns them on and off, under Helpers.
- **Vietnamese draft** Liên kết các từ tương ứng giữa lời nói và bản dịch. Khi trỏ: trỏ vào một từ. Gạch chân: màu biểu thị từ loại. Mũi tên: đường cong nối các từ. Bật tắt trong mục Công cụ hỗ trợ của menu thiết lập sẵn trên cửa sổ phụ đề.
- **Alternative** Các từ tương ứng trong lời nói và bản dịch được nối với nhau. Khi trỏ: trỏ vào từ để xem. Gạch chân: màu cho biết từ loại. Mũi tên: nối bằng đường cong. Bật tắt trong Công cụ hỗ trợ của menu thiết lập sẵn.
- **In context** Check the three display modes against their controls on a caption window. [panels.py](../../src/polyglotic_desktop/ui_next/panels.py)

## 14. Panels

- **English** Kana stays above each word's kanji. Romaji uses modified Hepburn; Both keeps kana above and adds romaji below.
- **Vietnamese** Kana nằm trên chữ kanji của từng từ. Romaji dùng hệ Hepburn cải biên. Cả hai giữ kana ở trên và thêm romaji ở dưới.
- **Alternative** Kana hiện trên phần kanji của mỗi từ. Romaji theo hệ Hepburn cải biên. Cả hai: kana ở trên, romaji ở dưới.
- **In context** Check familiar Vietnamese wording for the Japanese reading controls. [panels.py](../../src/polyglotic_desktop/ui_next/panels.py)

## 15. Settings

- **English** With Last %Ln hour(s) or Whole session, Quit asks first if a transcript of {line_limit} isn't saved.
- **Vietnamese** Khi chọn %Ln giờ gần nhất hoặc Cả phiên, ứng dụng sẽ hỏi trước khi thoát nếu bản ghi {line_limit} chưa được lưu.
- **Alternative** Với %Ln giờ gần nhất hoặc Cả phiên, Polyglotic sẽ hỏi trước khi thoát nếu bạn chưa lưu bản ghi {line_limit}.
- **In context** Check the sentence with the actual line-limit text substituted. [settings_page.py](../../src/polyglotic_desktop/ui_next/settings_page.py)

## 16. Settings

- **English** Version {version} is available. Your connection is metered, so it waits: Home can download it anyway.
- **Vietnamese** Đã có phiên bản {version}. Polyglotic chờ vì kết nối được đặt theo lưu lượng sử dụng. Bạn vẫn có thể tải xuống từ Trang chủ.
- **Alternative** Đã có phiên bản {version}. Kết nối này dùng gói dữ liệu theo lưu lượng nên Polyglotic tạm hoãn tải. Bạn vẫn có thể tải từ Trang chủ.
- **In context** Check a short, recognizable equivalent of the Windows network setting. [settings_page.py](../../src/polyglotic_desktop/ui_next/settings_page.py)

## 17. SettingsPopover

- **English** Display new lines
- **Vietnamese draft** Xen từng dòng dịch
- **Alternative** Xen bản dịch
- **In context** Check that this choice in Dòng dài suggests interleaved original and translated lines. [settings_popover.py](../../src/polyglotic_desktop/ui_next/settings_popover.py)

## 18. SettingsPopover

- **English** Grouped
- **Vietnamese draft** Gộp riêng bản gốc và bản dịch
- **Alternative** Gộp theo bản
- **In context** Check that the choice reads as all original lines followed by all translated lines. [settings_popover.py](../../src/polyglotic_desktop/ui_next/settings_popover.py)

## 19. Words

- **English** Every word available to export was already exported in this format. {name} is empty.
- **Vietnamese** Mọi từ đủ điều kiện đều đã xuất ở định dạng này. Tệp {name} rỗng.
- **Alternative** Tất cả từ có thể xuất đều đã được xuất ở định dạng này. Tệp {name} không có nội dung.
- **In context** Check that the previous-export explanation reads clearly before users open an empty file. [words_page.py](../../src/polyglotic_desktop/ui_next/words_page.py)

## 20. DictationSign

- **English** Re-speaking for {name} - let go to caption
- **Vietnamese** Đang nhắc lại cho {name} – thả phím để tạo phụ đề
- **Alternative** Đang nói thay cho {name} – thả phím để tạo phụ đề
- **In context** Check whether nói thay makes the source label and the use of the microphone easier to understand. [dictation_sign.py](../../src/polyglotic_desktop/ui_next/dictation_sign.py)

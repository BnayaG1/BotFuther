# -*- coding: utf-8 -*-
from pathlib import Path

p = Path(r"bot/handlers/router.py")
text = p.read_text(encoding="utf-8")
start = text.index("async def on_menu_callback")
end = text.index("async def on_assistant_callback")
new = r'''async def on_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data or not query.data.startswith("menu:"):
        return
    action = query.data.split(":", 1)[-1]
    chat_id = query.message.chat_id if query.message else telegram_chat_id(update)

    # יציאה מתרגול לנושא אחר — מוחקים את הודעות התרגיל מהצ'אט.
    if action in ("new", "formulas", "intro", "coupon") or action.startswith("mode:"):
        leave_session = get_solution_session(chat_id)
        if has_practice_chat_trail(chat_id) or (
            leave_session is not None and leave_session.from_practice
        ):
            await cleanup_practice_chat(context, chat_id)

    if action == "coupon":
        if not COUPON_ACCESS_ENABLED:
            await query.answer("מערכת הקופונים כבויה.", show_alert=True)
            return
        await query.answer()
        await _delete_callback_message(query)
        await _send_purchase_menu(context, chat_id)
        return
    if action == "formulas":
        await query.answer()
        await _delete_callback_message(query)
        await _send_formulas_menu(
            context,
            chat_id,
            user_id=telegram_user_id(update),
        )
        return
    if action == "intro":
        if not INTRO_AVAILABLE:
            await query.answer("המבוא בפיתוח ולא זמין כאן כרגע.", show_alert=True)
            return
        await query.answer()
        await _delete_callback_message(query)
        await _send_intro_opening(context, chat_id)
        return
    if action == "give_exercise":
        user_id = telegram_user_id(update)
        if COUPON_ACCESS_ENABLED and not has_practice_access(user_id):
            await query.answer()
            await _delete_callback_message(query)
            await cleanup_practice_chat(context, chat_id)
            await _send_content_locked(context, chat_id)
            return
        if count_exercises() <= 0:
            await query.answer("אין עדיין תרגילים מוכנים במאגר.", show_alert=True)
            return
        cool = exercise_bank_cooldown_remaining_sec(user_id)
        if cool is not None:
            mins = max(1, int((cool + 59) // 60))
            await query.answer(
                f"אפשר לקבל תרגיל נוסף בעוד כ-{mins} דקות.",
                show_alert=True,
            )
            return
        await query.answer()
        await _delete_callback_message(query)
        await cleanup_practice_chat(context, chat_id)
        begin_practice_chat_trail(chat_id)
        picked = pick_next_exercise_for_user(user_id)
        if picked is None:
            await _send_text_safe(context, chat_id, "אין עדיין תרגילים מוכנים במאגר.")
            return
        exercise_id, extracted = picked
        stored_image = get_exercise_image_path(exercise_id)
        photo_sent = False
        if stored_image is not None:
            try:
                with stored_image.open("rb") as photo:
                    sent = await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=photo,
                    )
                _track_sent_message(chat_id, sent)
                photo_sent = True
            except Exception as exc:
                log.warning(
                    "Failed to send stored exercise photo chat=%s id=%s: %s",
                    chat_id,
                    exercise_id,
                    exc,
                )
        if not photo_sent:
            problem_path = render_exercise_problem_png_temp(extracted)
            if problem_path is not None:
                try:
                    with problem_path.open("rb") as photo:
                        sent = await context.bot.send_photo(
                            chat_id=chat_id,
                            photo=photo,
                        )
                    _track_sent_message(chat_id, sent)
                    photo_sent = True
                except Exception as exc:
                    log.warning(
                        "Failed to send exercise photo chat=%s: %s", chat_id, exc
                    )
                finally:
                    problem_path.unlink(missing_ok=True)
        if not photo_sent:
            from bot.draft_format import extracted_to_draft_text

            draft_lines = extracted_to_draft_text(extracted).split("\n")
            data_text = "\n".join(draft_lines[2 : draft_lines.index("---")]).strip()
            sent = await _send_text_safe(context, chat_id, data_text)
            _track_sent_message(chat_id, sent)
        set_pending_bank_exercise(chat_id, exercise_id, extracted)
        keyboard = build_bank_solve_mode_keyboard()
        sent = await context.bot.send_message(
            chat_id=chat_id,
            text="איך תרצה/י לפתור את התרגיל?",
            reply_markup=keyboard,
        )
        _track_sent_message(chat_id, sent)
        return
    if action == "new":
        await query.answer()
        await _delete_callback_message(query)
        text = solve_mode_picker_intro_hebrew()
        keyboard = build_solve_mode_keyboard()
        await _send_text_safe(context, chat_id, text)
        await context.bot.send_message(
            chat_id=chat_id,
            text="בחר/י מצב:",
            reply_markup=keyboard,
        )
        return
    if action.startswith("mode:"):
        mode = parse_menu_mode_action(action)
        if mode is None:
            await query.answer()
            return
        await query.answer()
        await _delete_callback_message(query)
        prompt = select_solve_mode(chat_id, mode)
        await _send_text_safe(context, chat_id, prompt)
        return
    if action.startswith("bank:"):
        mode = parse_bank_mode_action(action)
        if mode is None:
            await query.answer()
            return
        await query.answer()
        await _delete_callback_message(query)
        pending = consume_pending_bank_exercise(chat_id)
        if pending is None:
            await _send_text_safe(
                context, chat_id, "אין תרגיל ממתין מהמאגר — לחץ/י שוב על «תרגול»."
            )
            return
        _exercise_id, bank_extracted = pending
        if int(_exercise_id) == _GENERATED_EXERCISE_ID:
            if isinstance(bank_extracted, dict):
                meta = dict(bank_extracted.get("meta") or {})
                meta.setdefault("source", "exercise_generator")
                meta["skip_vision_normalize"] = True
                bank_extracted = {**bank_extracted, "meta": meta}
        normalized = _bank_extracted_for_solve(bank_extracted)
        try:
            bank_solved = solve_extracted_beam(normalized)
        except Exception:
            bank_solved = {"result": {"reactions_ton": {}}}
        begin_image_session(chat_id, solve_mode=mode, from_practice=True)
        await deliver_after_draft_approve(
            context,
            chat_id,
            extracted=normalized,
            reply="",
            solved=bank_solved,
            draft_msg_id=None,
            deliver_notebook=_deliver_approved_solve,
            send_text=_send_text_safe,
            edit_draft_message=_edit_draft_message_safe,
        )
        return
    await query.answer()


'''
p.write_text(text[:start] + new + text[end:], encoding="utf-8")
print("ok")

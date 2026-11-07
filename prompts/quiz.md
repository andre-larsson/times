Task: you are the quiz editor. Write the paper's news quiz: {questions} multiple-choice questions on the
stories it ran since the last quiz (in <data>). Readers play it for fun, to see how much of the news
they caught.

The reader's interests:
{interests}

Picking stories
- Spread the questions over the period: at most {max_per_day} from any one day, and at least one from
  every day that has featured or medium stories.
- Spread them over the sections too: every section that has stories (AI, Tech, Gaming) gets at least
  one question, and no section more than {max_per_section}.
- Prefer featured and medium stories. A brief or gaming_news item works when its fact is in the
  headline or summary shown.
- One question per story; the biggest story of the period may get two.
- Ask about what a reader would remember or enjoy knowing: what was released, who did what, the key
  number, what changed and why it matters. Not a side detail buried in the story.
- Music: when a story touches music (AI music tools, game soundtracks, audio hardware, streaming), it
  makes a welcome question.
- Never repeat or closely rephrase a question in earlier_questions.

Writing a question
- question: one clear sentence, at most about 20 words, answerable from that story's facts shown in
  <data> (headline, dek, key points or summary). Don't refer to "the story" or "the article"; write it
  as a question about the world: "Which company…", "How much faster…".
- answer: the right answer, short: a name, a number or a few words.
- wrong_answers: exactly three. The same kind and length as the answer, believable to someone who
  half-remembers the news, and clearly wrong. No jokes, no "all of the above", no "none of these".
  When the story names alternatives (rival companies, other products, earlier figures), they make good
  wrong answers, as long as they're definitely not the answer to this question.
- Numbers: number + unit ("40%", "$1,000", "70B parameters"), and wrong numbers clearly apart from the
  right one (18% against 5%, 40% and 75%, not 18% against 19%).
- Don't give the answer away: the question mustn't repeat a word that only the right answer contains,
  and the right answer mustn't be longer, more specific or more carefully worded than the others.
- explanation: one or two sentences that confirm the answer and add one interesting detail from the
  same story. Plain and factual, in the house style.
- story_id: the id of the story the question comes from.
- Mix the difficulty, a few easy and a couple hard, and order the questions roughly easy to hard.

Off limits
- Hacker News points, comment counts and other site metrics; which outlet reported something; which
  day a story ran.
- Tragedies, deaths, crime victims, private individuals and partisan politics.
- Anything the story itself calls a rumor or unconfirmed.

Reply with questions, in quiz order.

---
title: "Entropy coding by a beginner for beginners - Part 7: ANS (rANS, FSE/tANS)"
date: 2024-03-11 00:00:02 +0200
categories: [compression]
tags: [arithmetic coding, compression, ANS]
math: true
---

## Introduction

*(Introduction is optional. TL; DR this part for people who are in process of understanding how ANS works, so you need to be familiar with ANS theory in some sort to be able follow with this part)*

While making a series of posts about entropy coding, it’s impossible not to mention ANS (Asymmetric Numeral System), an alternative method of encoding entorpy [proposed](https://arxiv.org/pdf/1311.2540v2.pdf) by Jarek Duda around 2009 (which was completed with the help of Jan Colet's parallel work on FSE). Unlike AC and PPM, we have at least three detailed guides about how to implement it and why it works at all, from people like [Charles Bloom](https://cbloomrants.blogspot.com/2014/02/02-18-14-understanding-ans-conclusion.html), [Fabian Giesen](https://fgiesen.wordpress.com/2014/02/02/rans-notes/) and [Jan Colet](https://fastcompression.blogspot.com/2014/01/fse-decoding-how-it-works.html), each of whom add their own code examples. If you've somewhere read or heard about ANS than ~98% chance you've seen links to their works.

Basically their material gives you the opportunity to understand how rANS and FSE/tANS work at all, doing so still remains a challenging task, especially for people who decided to deal with rANS before classic AC (one of whom I was since following Fabian’s blog for a long time). Like an absolute regular adequate person, I was trying to find some alternative resources on Google. However, these small number of alternative explanations that I found were basically just a mixture of the original works but in a much shorter volume (except few maybe) and don't answer on any of "why" question that I had. It can easily be the case that I am not their target audience, there are no questions. But in the end, I ended up that it would be much easier to continue digging into the works of people who make ANS theory work.

Although it is not hard to grasp the general idea behind how rANS and FSE/tANS works, but details of ”why” it works become not so obvious. These small pieces of puzzles, I always had the feeling that it’s something obvious, that it’s just in front of me, I need just to catch it, but I can’t because I don’t see it. After the 5th run of reading I stopped counting, but kept digging further because I understood that I would not find better material. I still think so. If you really want to understand how ANS work, you 100% need to read original works. So basically, I don’t see any sense in doing “another guide on rANS”. Instead, this article will be based on my notes where I make points about all these non-obvious things that I faced when I started to dig into rANS, FSE/tANS. This article is intended for people who have at least once run through the material that I have linked. Otherwise, everything written below will not bring much benefit, since I omit many things and use formula notation from the original article.

## rANS

To have the ability to encode entropy with saving information about fractional part, we need a buffer that will accumulate these fractions of bits, which essentially is our base. In the second part where we look at AC, such buffer was **low** and **high** values that we imagine infinitely approach to each other on x/p from MSB part. In the case of the rANS our buffer (base) will be just one integer that grows from LSB part.

You can imagine about how rANS work in two direction. The first is like growth of the number by entropy, and the second is like the alternation of numbers in an asymmetric numeral system, which is idea behind ANS. Although the second way is "canonical" it can be confusing, especially if you concentrate on a slot repetition cycle that takes a symbol (one of the best alternative [explanation](https://bjlkeng.io/posts/lossless-compression-with-asymmetric-numeral-systems/) concentrates on this aspect, author just much better at math that I am).

Let’s look at the simple example of encoding some values in one integer in base 2 where symbols have equal probability.

![](/assets/img/post/etr-enc-7/bin.png){: w="600"}

For base of 2 it is just shift plus bit to encode. Current state of integer lies directly on encoded bits so it can been easily seen what was encoded in this integer. This example very easy to understand but as you can see we already skipping some slot repetition cycle due to multiplication by base. In this case it intuitive understandable why this happened, thought.

What If we whant to encode symbol that have probability like 1/4 and 3/4. Their cycles should now conventionally look like this.

![](/assets/img/post/etr-enc-7/seq0.png){: w="600"}

But as you already should know rANS operate with states like this.

![](/assets/img/post/etr-enc-7/seq1.png){: w="600"}

In order to account for symbol probability (e.g. it may be not a power of two), we need to change the formula. Now the increment of the number should be done like $$base * x$$ where $$x = CDF[Total]/Fs$$ (or $$base / x$$ were $$x = Fs/CDF[Total]$$ ). To make this at least somehow work we must rearrange multiplication because we work with integer, as in the classic AC. For now, let’s write it like $(x*M)/Fs + Bs$, that in theory should give the most accurate increase. Adding **Bs** for distinguish encoded symbols.

I haven’t put any numerical representation for states in the last two pictures on purpose because what exactly should be there? We obviously need more space to have the ability to encode fraction of a bit. In addition, in this case, the more there will be a difference between a start value of a base and maximum value of CDF, the more precise the increase will be.

We can say that $$log_2(x) \;– \;log_2(M)$$ is a **k** coefficient.

![](/assets/img/post/etr-enc-7/prec.png){: w="450"}

Of course, like in the case with AC we can’t think about encoding in isolation from decoding. Like in the example with encoding with base 2, for decoding, we need to do (x%M). The main difference now is the uneven growth of our base. In addition, at (x%M) for each symbol that we have, we get not just one value but rather a range of values between $$[Bs, Bs+Fs)$$. Both of these factors lead to the fact that by encoding symbol like $$(x*M)/Fs + Bs$$, latter at the decoding side $$(x*Fs)/M \;–\; Bs$$, we will not get to the right previous state of our base.

![](/assets/img/post/etr-enc-7/rans_wrong.png){: w="500"}

At each particular step of encoding, it may seems that after we take reciprocal, we get roughly right answer, but actually, we lose information about where we are in ANS automate. Adding (x%F) in this case also will not help because we shuffle bits of the base (and with it lower M bits) too much.

For doing decoding right, lower M bits must not be involved in the division. To avoid this, we are changing the process of encoding like this $$(x\;/\;FS)*M \;+\; (x\;\%\;FS)\; +\; Bs$$. The (x%FS) is our lost bits at the division, also without this information we will not be able to reach the right previous state at the decoding step.

![](/assets/img/post/etr-enc-7/ans_right.png){: w="600"}


During decoding we get the same value, but this time we actually are able to roll back the state. I highlight **(x%M) – Bs** at the decoding for a  purpose because it is basically one operation that allow us to get (x%FS) fraction back, value of which lies in the $$[Bs; Bs + Fs)$$ range. So, basically, operation (x%FS) allows us not only not to break an automate but also serves for carrying fraction of bits to lower M bits.

So you may notice that by encoding symbol C first, for example, we have no choice but to increase our base at least by Bs of symbol C. That is, during encoding, sometimes we will increase our fraction part more than we would like. Sound not very optimal but it’s not that bad in practice. I took test files end encoded them as all their symbol were written sequentially. Despite the fact that the final entropy of rANS state did differs, it actually did not differ much to make a difference in the final result. The final state may be different depending on the encoder parameters.

*(rANS with 1 byte at a time normalization, table log2 = 12, L = 23 bits)*

| name  | orig. log2 | seq. log2 |
| :---- | :--------: | :-------: |
| book1 | 25.7156    |  25.0355  |
| geo   | 30.1495    |  29.8343  |
| obj2  | 25.9816    |  25.5086  |
| pic   | 27.8668    |  27.6645  |

The point being that this not play a big role. The main loses happens due to several other reason. First one is normalization, since we conventionally build a large number each time we are doing normalization, by throwing off lower bits, we are getting slightly off. The second one is because we are doing increment on the fractional part not as precise as it can be.

## FSE/tANS

For me, one of the non-obvious things was why we always end up in the state that we actually need at encoding/decoding? Let’s look at a simple example with encoding a symbol that have a power of two probability.

Although the table looks like this

![](/assets/img/post/etr-enc-7/tans0.png){: w="600"}

But what we actually storing in memory is something like this.

![](/assets/img/post/etr-enc-7/tans1.png){: w="600"}

Symbols B and C have the same valid coding interval [Fs, 2Fs-1], i.e., after normalization, from any state, we get same value for both of them. However, depending on the symbol we choose, the offset that belong to this symbol gets us to the proper state. For example, let’s start from state 16. We throw away 2 LSB and get 4. Then, depending on the symbol B or C we get to state 17 or 19.

In the example above, if you try to encode the same symbol several times in a row, you end up staying in the same state since neither of these symbol has fractional part that it should carry to the buffer. Unlike in the example bellows.

![](/assets/img/post/etr-enc-7/tans2.png){: w="600"}

This look more like something real. Now, if we keep encoding symbol A, even though we write one bit, the base will change by $$log_2(19)\; – \;log_2(16) = 0.25$$ bits (if the base had more resolution, then precisions would be higher, of course). Also, this time we actually need the **Thr** value because now it tell as when we need to output **n + 1** bits for current symbol so we can stay in the [Fs, 2Fs-1] range affter normalization. By the way, as you can see, value of Thr can match, since in this case, $$-log_2(B)$$ and $$-log_2(С)$$ have the same fractional part.

At first, since we lowering our base by **n + 1** bits instead of **n** bits, it may seems that we decrease the count of available state for symbol to witch we can jump by a factor of 2, but it’s not true. It is all depends on the fraction of bits that the symbol has. Below, the graph shows the frequency of the symbol in x-axis and the maximum number of states it can reach after normalization in y-axis (L = 2048).

![](/assets/img/post/etr-enc-7/graph.jpg)

In this way, a symbol with frequency of $-log_2(1025/2048) = 0.9986$ very rarely needs 0 bits, so it will write **n + 1** bits for most of its code space. A symbol with a frequency of $-log_2(1023/2048)= 1.0014$ almost never needs 2 bits, and after normalization, it only goes into an **n-bit** slot.

## Why [Fs, 2Fs-1] for FSE/tANS?

Some may notice that for rANS [Fs, 2Fs-1] would be mean that we can normalize only bit at a time. So why with tANS we read/write as many as we need? Or why with rANS we can’t read/write as many as we need? Besides the fact that working with 2^n bits you can, in theory, simplify your bits IO, we remember that you can’t think about the encoder without decoder and vice versa. For making streaming ANS work, we need to know when we need to throw off or get a bits exactly. One of the main features of the ANS is precisely the fact that we know in advance our normalizing interval, unlike in the classic AC. This is possible thanks to the b-uniqueness property and the satisfaction of the properties that bring up with it, which guarantee that the encoder and decoder cannot have two valid states:

$$
\begin{flalign}
&L = kM;&\\
&I = [L:bL);&\\
&I_s = \{x|C(s, x) ∈ I\};&
\end{flalign}
$$

Let’s imagine what gonna happen if we would write only as much bits at the rANS normalization stage as symbol requires. If during encoding of symbol **s**, we've thrown off 5 bits to let it stay in a valid range, then at decoding, before doing (x%M) operation for symbol **s - 1**, we need at first normalize state back to as it was before encoding symbol **s**, but we don’t know exactly how much bits we need to read, we know that we just bellow the value of L (we in theory know that symbol take from **n** to **n + 1** bits, though). If we start reading bits one by one, then we may think that L + 1 is a valid state, but if the state from which we've made normalization actually was L + 2, then that’s the end of story. So, to keep encoder and decoder in sync we need to read and write same amount of bits and at the same time. Because of the fact that we don’t know precise property of each state, we tweak **b**, **k** and **M** properties to adjust such parameters as:
- Coding resolution
- How often we are doing normalization
- How many bits normalization is required

But as you already may guess, if we would have more information about each state then we can be more flexible in term of normalization at encoding and decoding. So in the previous situation, as long as we know exactly from which place in the table the symbol **s** got to state **x** and how much the encoder recorded from this state, we can accurately obtain the previous state for the symbol **s - 1**.

## ANS in real word

Is the ANS useful at practice? Of course! Two fastest LZ codec use them for their needs, [zstd](https://github.com/facebook/zstd) which can be said already become a standard choice, and [Oodle](https://www.radgametools.com/oodle.htm) licenses of which were purchased for use in PS5 and Unreal Engine. Dropbox also [experimented](https://dropbox.tech/infrastructure/building-better-compression-together-with-divans) with ANS by stacking multiple contexts for [CDF blending](https://fgiesen.wordpress.com/2015/02/20/mixing-discrete-probability-distributions/), but I’m not sure if they really use it internally. 